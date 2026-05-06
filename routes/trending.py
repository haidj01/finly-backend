import asyncio
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter

router = APIRouter(prefix="/api/trending")

DATA              = "https://data.alpaca.markets"
MASSIVE_API_URL   = "https://api.massive.com"
FMP_BASE          = "https://financialmodelingprep.com/stable"
EDGAR_BASE        = "https://data.sec.gov"
EDGAR_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
EDGAR_ARCHIVES    = "https://www.sec.gov/Archives/edgar/data"
CLAUDE_API_URL    = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL      = "claude-sonnet-4-6"

MIN_PRICE              = 5.0
_CACHE_TTL_OPEN        = 300
_CACHE_TTL_CLOSED      = 3600
_CACHE_FMP_TTL         = 1800
_CACHE_CIK_TTL         = 86400   # 1일 — CIK 매핑은 거의 안 바뀜
_INSIDER_LOOKBACK_DAYS = 7

_cache: dict     = {"data": None, "ts": 0}
_fmp_cache: dict = {"profiles": {}, "screener": [], "ts": 0}
_cik_cache: dict = {"map": {}, "ts": 0}

_SECTOR_PE: dict[str, float] = {
    "Technology":              28.0,
    "Healthcare":              22.0,
    "Financial Services":      14.0,
    "Consumer Cyclical":       18.0,
    "Consumer Defensive":      20.0,
    "Industrials":             20.0,
    "Energy":                  15.0,
    "Utilities":               18.0,
    "Real Estate":             25.0,
    "Basic Materials":         15.0,
    "Communication Services":  22.0,
}

_EDGAR_HEADERS = {"User-Agent": "finly haidj01@gmail.com"}


def _is_market_open() -> bool:
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return False
    h, m = now.hour, now.minute
    return (h > 9 or (h == 9 and m >= 30)) and h < 16


def _alpaca_headers():
    return {
        "APCA-API-KEY-ID":     os.environ["ALPACA_API_KEY"],
        "APCA-API-SECRET-KEY": os.environ["ALPACA_API_SECRET"],
    }


def _claude_headers():
    return {
        "Content-Type":      "application/json",
        "x-api-key":         os.environ["CLAUDE_API_KEY"],
        "anthropic-version": "2023-06-01",
    }


def _fmp_api_key() -> str:
    return os.environ.get("FMP_API_KEY", "")


# ── Step 1a: Alpaca 후보군 수집 ───────────────────────────────────────────────

async def _fetch_snapshots(symbols: list[str]) -> dict[str, dict]:
    if not symbols:
        return {}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.get(
                f"{DATA}/v2/stocks/snapshots",
                params={"symbols": ",".join(symbols)},
                headers=_alpaca_headers(),
            )
        if res.status_code != 200:
            print(f"[Alpaca snapshots] {res.status_code}: {res.text[:200]}")
            return {}

        result = {}
        is_open = _is_market_open()
        for sym, data in res.json().items():
            if is_open:
                latest_trade = data.get("latestTrade", {})
                price = (
                    latest_trade.get("p")
                    or data.get("minuteBar", {}).get("c")
                    or data.get("dailyBar", {}).get("c", 0)
                )
            else:
                price = data.get("dailyBar", {}).get("c") or data.get("latestTrade", {}).get("p", 0)

            prev_close = data.get("prevDailyBar", {}).get("c", 0)
            change = round(price - prev_close, 4) if prev_close else 0.0
            pct    = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0.0
            result[sym] = {"price": round(price, 2), "change": change, "percent_change": pct}
        return result
    except Exception as e:
        print(f"[Alpaca snapshots] 예외: {e}")
        return {}


async def _fetch_most_actives(top: int = 20) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.get(
                f"{DATA}/v1beta1/screener/stocks/most-actives",
                params={"by": "volume", "top": top},
                headers=_alpaca_headers(),
            )
        if res.status_code != 200:
            print(f"[Alpaca most-actives] {res.status_code}: {res.text[:200]}")
            return []
        actives = res.json().get("most_actives", [])
    except Exception as e:
        print(f"[Alpaca most-actives] 예외: {e}")
        return []

    syms = [s["symbol"] for s in actives]
    snapshots = await _fetch_snapshots(syms)
    for s in actives:
        snap = snapshots.get(s["symbol"], {})
        s["price"]          = snap.get("price", 0)
        s["change"]         = snap.get("change", 0)
        s["percent_change"] = snap.get("percent_change", 0)
    return actives


async def _fetch_movers(top: int = 10) -> tuple[list[dict], list[dict]]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.get(
                f"{DATA}/v1beta1/screener/stocks/movers",
                params={"top": top},
                headers=_alpaca_headers(),
            )
        if res.status_code != 200:
            print(f"[Alpaca top-movers] {res.status_code}: {res.text[:200]}")
            return [], []
        data = res.json()
        return data.get("gainers", []), data.get("losers", [])
    except Exception as e:
        print(f"[Alpaca top-movers] 예외: {e}")
        return [], []


# ── Step 1b: FMP 스크리너 + 프로필 (30분 캐시) ───────────────────────────────

async def _fetch_fmp_screener(limit: int = 10) -> list[dict]:
    key = _fmp_api_key()
    if not key:
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.get(
                f"{FMP_BASE}/stock-screener",
                params={
                    "marketCapMoreThan": 1_000_000_000,
                    "country":          "US",
                    "exchange":         "NYSE,NASDAQ",
                    "limit":            limit,
                    "apikey":           key,
                },
            )
        if res.status_code != 200:
            print(f"[FMP screener] {res.status_code}: {res.text[:200]}")
            return []
        return res.json() or []
    except Exception as e:
        print(f"[FMP screener] 예외: {e}")
        return []


async def _fetch_fmp_profiles(symbols: list[str]) -> dict[str, dict]:
    key = _fmp_api_key()
    if not key or not symbols:
        return {}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.get(
                f"{FMP_BASE}/profile",
                params={"symbol": ",".join(symbols), "apikey": key},
            )
        if res.status_code != 200:
            print(f"[FMP profile] {res.status_code}: {res.text[:200]}")
            return {}
        items = res.json() or []
        return {p["symbol"]: p for p in items if isinstance(p, dict)}
    except Exception as e:
        print(f"[FMP profile] 예외: {e}")
        return {}


async def _get_fmp_data(candidates: list[dict]) -> tuple[list[dict], dict[str, dict]]:
    now = time.time()
    if _fmp_cache["ts"] and now - _fmp_cache["ts"] < _CACHE_FMP_TTL:
        return _fmp_cache["screener"], _fmp_cache["profiles"]

    syms = list({s["symbol"] for s in candidates})
    screener_raw, profiles = await asyncio.gather(
        _fetch_fmp_screener(10),
        _fetch_fmp_profiles(syms),
    )

    screener: list[dict] = []
    for item in screener_raw:
        sym = item.get("symbol", "")
        if not sym:
            continue
        screener.append({
            "symbol":         sym,
            "price":          float(item.get("price", 0) or 0),
            "change":         0.0,
            "percent_change": float(item.get("changesPercentage", 0) or 0),
            "volume":         int(item.get("volume", 0) or 0),
        })

    _fmp_cache["screener"] = screener
    _fmp_cache["profiles"] = profiles
    _fmp_cache["ts"]       = now
    return screener, profiles


# ── Step 1c: FMP 뉴스 (Claude 프롬프트 보강) ─────────────────────────────────

async def _fetch_fmp_news(symbols: list[str]) -> dict[str, list[str]]:
    """최근 뉴스 헤드라인. {sym: [headline, ...]} 반환"""
    key = _fmp_api_key()
    if not key or not symbols:
        return {}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.get(
                f"{FMP_BASE}/news",
                params={"tickers": ",".join(symbols), "limit": 30, "apikey": key},
            )
        if res.status_code != 200:
            print(f"[FMP news] {res.status_code}: {res.text[:200]}")
            return {}
        articles = res.json() if isinstance(res.json(), list) else []
        news_map: dict[str, list[str]] = {}
        for article in articles:
            sym   = article.get("symbol", "")
            title = article.get("title", "") or article.get("headline", "")
            if sym and title:
                news_map.setdefault(sym, []).append(title)
        return news_map
    except Exception as e:
        print(f"[FMP news] 예외: {e}")
        return {}


# ── Step 1d: Polygon 옵션 플로우 (call/put 비율) ─────────────────────────────

async def _fetch_polygon_options_flow(symbols: list[str]) -> dict[str, dict]:
    """콜/풋 거래량 비율로 bullish_ratio 계산. {sym: {bullish_ratio, call_vol, put_vol}} 반환"""
    api_key = os.environ.get("MASSIVE_API_KEY", "")
    if not api_key or not symbols:
        return {}

    results: dict[str, dict] = {}

    async def _fetch_one(client: httpx.AsyncClient, sym: str) -> None:
        try:
            res = await client.get(
                f"{MASSIVE_API_URL}/v3/snapshot/options/{sym}",
                params={"limit": 50, "sort": "volume", "order": "desc", "apiKey": api_key},
            )
            if res.status_code != 200:
                return
            contracts = res.json().get("results", [])
            call_vol = put_vol = 0
            for c in contracts:
                vol   = int(c.get("day", {}).get("volume", 0) or 0)
                ctype = c.get("details", {}).get("contract_type", "")
                if ctype == "call":
                    call_vol += vol
                elif ctype == "put":
                    put_vol += vol
            total = call_vol + put_vol
            if total > 0:
                results[sym] = {
                    "bullish_ratio": round(call_vol / total, 3),
                    "call_vol":      call_vol,
                    "put_vol":       put_vol,
                }
        except Exception as e:
            print(f"[Polygon options {sym}] 예외: {e}")

    async with httpx.AsyncClient(timeout=30) as client:
        await asyncio.gather(*[_fetch_one(client, sym) for sym in symbols])
    return results


# ── Step 1e: SEC EDGAR Form 4 내부자 거래 ─────────────────────────────────────

async def _load_cik_map() -> dict[str, int]:
    """티커 → CIK 매핑. 1일 캐시"""
    now = time.time()
    if _cik_cache["ts"] and now - _cik_cache["ts"] < _CACHE_CIK_TTL:
        return _cik_cache["map"]
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.get(EDGAR_TICKERS_URL, headers=_EDGAR_HEADERS)
        if res.status_code != 200:
            print(f"[EDGAR tickers] {res.status_code}")
            return _cik_cache["map"]
        cik_map = {v["ticker"]: int(v["cik_str"]) for v in res.json().values()}
        _cik_cache["map"] = cik_map
        _cik_cache["ts"]  = now
        return cik_map
    except Exception as e:
        print(f"[EDGAR tickers] 예외: {e}")
        return _cik_cache["map"]


def _parse_form4_xml(xml_text: str) -> dict:
    """Form 4 XML 파싱. A=매수, D=매도"""
    buys = sells = 0
    try:
        root = ET.fromstring(xml_text)
        for tx in (
            root.findall(".//nonDerivativeTransaction")
            + root.findall(".//derivativeTransaction")
        ):
            code_el = tx.find(".//transactionAcquiredDisposedCode/value")
            if code_el is not None and code_el.text:
                code = code_el.text.strip().upper()
                if code == "A":
                    buys += 1
                elif code == "D":
                    sells += 1
    except Exception:
        pass
    return {"buys": buys, "sells": sells}


async def _fetch_insider_for_symbol(
    client: httpx.AsyncClient, sym: str, cik: int
) -> tuple[str, dict]:
    """submissions API → 최근 7일 Form 4 → XML 파싱"""
    cutoff = (datetime.now() - timedelta(days=_INSIDER_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    result = {"buys": 0, "sells": 0}
    try:
        res = await client.get(
            f"{EDGAR_BASE}/submissions/CIK{cik:010d}.json",
            headers=_EDGAR_HEADERS,
        )
        if res.status_code != 200:
            return sym, result

        recent   = res.json().get("filings", {}).get("recent", {})
        forms    = recent.get("form", [])
        dates    = recent.get("filingDate", [])
        accnos   = recent.get("accessionNumber", [])
        prim_docs = recent.get("primaryDocument", [])

        # 최근 7일 Form 4만 추출 (최대 3건 XML 파싱)
        form4s = [
            (accnos[i], prim_docs[i])
            for i in range(len(forms))
            if forms[i] == "4" and i < len(dates) and dates[i] >= cutoff
        ][:3]

        for accession, doc in form4s:
            acc_clean = accession.replace("-", "")
            url = f"{EDGAR_ARCHIVES}/{cik}/{acc_clean}/{doc}"
            try:
                xml_res = await client.get(url, headers=_EDGAR_HEADERS)
                if xml_res.status_code == 200:
                    parsed = _parse_form4_xml(xml_res.text)
                    result["buys"]  += parsed["buys"]
                    result["sells"] += parsed["sells"]
            except Exception:
                pass
    except Exception as e:
        print(f"[EDGAR {sym}] 예외: {e}")
    return sym, result


async def _fetch_insider_activity(
    symbols: list[str], cik_map: dict[str, int]
) -> dict[str, dict]:
    """모든 후보 종목의 최근 7일 내부자 거래. {sym: {buys, sells}} 반환"""
    pairs = [(sym, cik_map[sym]) for sym in symbols if sym in cik_map]
    if not pairs:
        return {}
    async with httpx.AsyncClient(timeout=30) as client:
        tasks = [_fetch_insider_for_symbol(client, sym, cik) for sym, cik in pairs]
        return dict(await asyncio.gather(*tasks))


# ── Step 2: Massive 전일 거래량 ───────────────────────────────────────────────

async def _fetch_prev_volumes_massive(symbols: list[str]) -> dict[str, float]:
    if not symbols:
        return {}
    api_key = os.environ.get("MASSIVE_API_KEY", "")
    if not api_key:
        print("[Massive] MASSIVE_API_KEY 없음 — 전일 거래량 스킵")
        return {}

    results: dict[str, float] = {}

    async def _fetch_one(client: httpx.AsyncClient, sym: str) -> None:
        try:
            res = await client.get(
                f"{MASSIVE_API_URL}/v2/aggs/ticker/{sym}/prev",
                params={"apiKey": api_key},
            )
            if res.status_code == 200:
                items = res.json().get("results", [])
                if items:
                    results[sym] = float(items[0].get("v", 0))
        except Exception as e:
            print(f"[Massive prev] {sym} 예외: {e}")

    async with httpx.AsyncClient(timeout=30) as client:
        await asyncio.gather(*[_fetch_one(client, sym) for sym in symbols])
    return results


# ── Step 3: 스코어링 ──────────────────────────────────────────────────────────
# vol(35) + chg(25) + liq(10) + fundamental(15) + flow(10) + insider(5) = 100pt

def _calc_fundamental_score(sym: str, fmp_map: dict, price: float) -> float:
    fmp       = fmp_map.get(sym, {})
    pe        = fmp.get("pe")
    sector_pe = _SECTOR_PE.get(fmp.get("sector", ""), 20.0)
    dcf       = fmp.get("dcf")
    score = 0.0
    if pe and pe > 0:
        if pe < sector_pe * 0.8:
            score += 11.0
        elif pe < sector_pe:
            score += 6.0
    if dcf and price and dcf > price * 1.10:
        score += 4.0
    return score


def _calc_flow_score(sym: str, flow_map: dict) -> float:
    bullish_ratio = flow_map.get(sym, {}).get("bullish_ratio", 0.5)
    return max(bullish_ratio - 0.5, 0.0) * 20  # 0.5→0pt, 1.0→10pt


def _calc_insider_score(sym: str, insider_map: dict) -> float:
    insider = insider_map.get(sym, {})
    buys    = insider.get("buys", 0)
    sells   = insider.get("sells", 0)
    if buys > 0 and buys >= sells:
        return 5.0
    if buys > 0:
        return 2.0
    return 0.0


def _score_stock(
    stock: dict,
    prev_vol_map: dict,
    fmp_map: dict,
    flow_map: dict,
    insider_map: dict,
) -> float:
    sym       = stock.get("symbol", "")
    today_vol = float(stock.get("volume", 0) or 0)
    prev_vol  = float(prev_vol_map.get(sym, 0) or 0)
    price     = float(stock.get("price", 0) or 0)
    chg_pct   = float(stock.get("percent_change", 0) or 0)

    vol_score = min(today_vol / prev_vol / 3.0, 1.0) * 35 if prev_vol > 0 else 0.0

    if -1 <= chg_pct <= 3:
        chg_score = 25.0
    elif 3 < chg_pct <= 7:
        chg_score = 17.0
    elif 7 < chg_pct <= 10:
        chg_score = 8.0
    else:
        chg_score = 0.0

    liq_score = 10.0 if today_vol * price >= 1_000_000 else 0.0

    return (
        vol_score
        + chg_score
        + liq_score
        + _calc_fundamental_score(sym, fmp_map, price)
        + _calc_flow_score(sym, flow_map)
        + _calc_insider_score(sym, insider_map)
    )


# ── Step 4: Claude 분석 ───────────────────────────────────────────────────────

def _build_stock_line(s: dict, fmp_map: dict, news_map: dict) -> str:
    sym   = s["symbol"]
    price = s.get("price", 0)
    chg   = s.get("percent_change", 0)
    vol   = int(s.get("volume", 0)) // 1000
    fmp   = fmp_map.get(sym, {})

    pe        = fmp.get("pe")
    sector    = fmp.get("sector", "")
    sector_pe = _SECTOR_PE.get(sector)
    dcf       = fmp.get("dcf")

    pe_str  = f" PE:{pe:.1f}/섹터:{sector_pe}" if pe and sector_pe else ""
    dcf_str = ""
    if dcf and price:
        upside  = (dcf - price) / price * 100
        dcf_str = f" DCF:${dcf:.0f}({upside:+.0f}%)"
    sec_str  = f" [{sector}]" if sector else ""
    news     = news_map.get(sym, [])
    news_str = f" 뉴스:{news[0][:40]}" if news else ""

    return (
        f"{sym} ${price:.2f} {'+' if chg >= 0 else ''}{chg:.2f}%"
        f" 거래량{vol}K{pe_str}{dcf_str}{sec_str}{news_str}"
    )


async def _analyze(
    stocks: list[dict], fmp_map: dict, news_map: dict
) -> dict[str, dict]:
    if not stocks:
        return {}

    lines = [_build_stock_line(s, fmp_map, news_map) for s in stocks]

    syms   = ", ".join(s["symbol"] for s in stocks)
    prompt = (
        "미국 주식 데이터:\n" + "\n".join(lines) + "\n\n"
        f"각 종목({syms})을 분석해 JSON으로만 반환. 다른 텍스트 없이.\n"
        '{"SYM":{"reason":"주목이유25자이내한국어","risk":"위험20자이내또는null",'
        '"confidence":2,"analyst":"매수","growth":"+12%EPS(YoY)","buy_pick":true}}\n\n'
        "reason=거래량+펀더멘털+뉴스 종합근거(제공된 PE/DCF/뉴스 활용), "
        "risk=주요위험(없으면null), "
        "confidence=1추측/2간접정보/3명확근거(FMP수치있으면3가능), "
        "analyst=제공된PE·DCF·섹터 기준 매수/중립/매도, "
        "growth=EPS또는매출성장률(모르면null), "
        "buy_pick=confidence>=2이고 긍정모멘텀이고 저평가신호있으면true (전체30~50%만true)"
    )
    body = {
        "model":      CLAUDE_MODEL,
        "max_tokens": 1024,
        "messages":   [{"role": "user", "content": prompt}],
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post(CLAUDE_API_URL, headers=_claude_headers(), json=body)
        if res.status_code != 200:
            print(f"[Claude trending] {res.status_code}: {res.text[:200]}")
            return {}
        text  = next((b["text"] for b in res.json().get("content", []) if b["type"] == "text"), "{}")
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(match.group() if match else "{}")
    except Exception as e:
        print(f"[Claude trending] 예외: {e}")
        return {}


# ── 정규화 ────────────────────────────────────────────────────────────────────

def _normalize(
    raw: dict,
    category: str,
    reason_map: dict,
    fmp_map: dict,
    ctx: dict,
) -> dict:
    sym  = raw.get("symbol", "")
    info = reason_map.get(sym) or {}
    if not isinstance(info, dict):
        info = {"reason": str(info)}
    fmp = fmp_map.get(sym, {})

    pe_val    = fmp.get("pe")
    sector    = fmp.get("sector", "") or ""
    sector_pe = _SECTOR_PE.get(sector)
    dcf       = fmp.get("dcf")
    price     = float(raw.get("price", 0) or 0)

    flow    = ctx["flow"].get(sym, {})
    insider = ctx["insider"].get(sym, {})
    news    = ctx["news"].get(sym, [])

    return {
        "sym":               sym,
        "price":             round(price, 2),
        "change":            round(float(raw.get("change", 0)), 2),
        "chg_pct":           round(float(raw.get("percent_change", 0)), 2),
        "volume":            int(raw.get("volume", 0)),
        "category":          category,
        "reason":            info.get("reason", ""),
        "risk":              info.get("risk"),
        "confidence":        info.get("confidence"),
        "pe":                round(pe_val, 1) if pe_val else None,
        "sector_pe":         sector_pe,
        "analyst":           info.get("analyst"),
        "growth":            info.get("growth"),
        "buy_pick":          bool(info.get("buy_pick", False)),
        "sector":            sector or None,
        "dcf":               round(dcf, 2) if dcf else None,
        "dcf_upside":        round((dcf - price) / price * 100, 1) if dcf and price else None,
        "mkt_cap":           fmp.get("mktCap"),
        # Polygon 옵션 플로우
        "has_flow_alert":    sym in ctx["flow"],
        "flow_bullish_ratio": flow.get("bullish_ratio"),
        "call_vol":          flow.get("call_vol"),
        "put_vol":           flow.get("put_vol"),
        # SEC EDGAR 내부자 거래
        "insider_buys":      insider.get("buys", 0),
        "insider_sells":     insider.get("sells", 0),
        # FMP 뉴스
        "news_headline":     news[0] if news else None,
    }


# ── 라우터 ────────────────────────────────────────────────────────────────────

@router.get("")
async def get_trending():  # pylint: disable=too-many-locals
    now = time.time()
    ttl = _CACHE_TTL_OPEN if _is_market_open() else _CACHE_TTL_CLOSED
    if _cache["data"] and now - _cache["ts"] < ttl:
        return _cache["data"]

    # Step 1: 후보군 수집 + CIK 맵 병렬 로드
    (actives_raw, (gainers_raw, losers_raw), cik_map) = await asyncio.gather(
        _fetch_most_actives(20),
        _fetch_movers(10),
        _load_cik_map(),
    )

    # 페니스톡 제거 + 중복 제거
    actives_raw = [s for s in actives_raw if s.get("price", 0) >= MIN_PRICE]
    gainers_raw = [s for s in gainers_raw if s.get("price", 0) >= MIN_PRICE]
    losers_raw  = [s for s in losers_raw  if s.get("price", 0) >= MIN_PRICE]
    active_syms  = {s["symbol"] for s in actives_raw}
    gainers_raw  = [s for s in gainers_raw if s["symbol"] not in active_syms]
    losers_raw   = [s for s in losers_raw  if s["symbol"] not in active_syms]
    alpaca_candidates = actives_raw + gainers_raw + losers_raw

    # Step 1b: FMP 스크리너 + 프로필 (30분 캐시)
    fmp_screener, fmp_profiles = await _get_fmp_data(alpaca_candidates)
    alpaca_syms      = {s["symbol"] for s in alpaca_candidates}
    fmp_screener_new = [
        s for s in fmp_screener
        if s["symbol"] not in alpaca_syms and s.get("price", 0) >= MIN_PRICE
    ]
    fmp_new_syms = [s["symbol"] for s in fmp_screener_new if s["symbol"] not in fmp_profiles]
    if fmp_new_syms:
        extra = await _fetch_fmp_profiles(fmp_new_syms)
        fmp_profiles.update(extra)

    all_candidates = alpaca_candidates + fmp_screener_new
    all_syms       = list({s["symbol"] for s in all_candidates})

    # Step 1c~1e + Step 2: 보조 데이터 병렬 수집
    prev_vol_map, flow_map, insider_map, news_map = await asyncio.gather(
        _fetch_prev_volumes_massive(all_syms),
        _fetch_polygon_options_flow(all_syms),
        _fetch_insider_activity(all_syms, cik_map),
        _fetch_fmp_news(all_syms),
    )

    # Step 3: 스코어링 → 상위 10종목 (중복 심볼 제거)
    scored = sorted(
        all_candidates,
        key=lambda s: _score_stock(s, prev_vol_map, fmp_profiles, flow_map, insider_map),
        reverse=True,
    )
    seen  = set()
    top10 = []
    for s in scored:
        sym = s["symbol"]
        if sym not in seen:
            seen.add(sym)
            top10.append(s)
        if len(top10) >= 10:
            break

    # 카테고리 매핑
    gainer_syms       = {s["symbol"] for s in gainers_raw}
    fmp_screener_syms = {s["symbol"] for s in fmp_screener_new}

    def _category(sym: str) -> str:
        if sym in fmp_screener_syms:
            return "fmp_pick"
        if sym in active_syms:
            return "most_active"
        if sym in gainer_syms:
            return "gainer"
        return "loser"

    # Step 4: Claude 분석 (뉴스 컨텍스트 포함)
    reason_map = await _analyze(top10, fmp_profiles, news_map)

    ctx = {"flow": flow_map, "insider": insider_map, "news": news_map}
    all_normalized = [
        _normalize(s, _category(s["symbol"]), reason_map, fmp_profiles, ctx)
        for s in top10
    ]
    picks = [s for s in all_normalized if s["buy_pick"]]

    result = {"picks": picks}
    _cache["data"] = result
    _cache["ts"]   = now
    return result
