import asyncio
import json
import os
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter

router = APIRouter(prefix="/api/trending")

DATA              = "https://data.alpaca.markets"
MASSIVE_API_URL   = "https://api.massive.com"
FMP_BASE          = "https://financialmodelingprep.com/stable"
CLAUDE_API_URL    = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL      = "claude-sonnet-4-6"
MIN_PRICE         = 5.0
_CACHE_TTL_OPEN   = 300   # 장중 5분
_CACHE_TTL_CLOSED = 3600  # 장 마감 1시간
_CACHE_FMP_TTL    = 1800  # FMP 30분 (펀더멘털은 자주 안 바뀜, 250 req/day 절약)
_cache: dict      = {"data": None, "ts": 0}
_fmp_cache: dict  = {"profiles": {}, "screener": [], "ts": 0}

# 섹터별 평균 PER (벤치마크)
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
    """저PER 대형주 후보군 추가 발굴 (1 req)"""
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
    """PE, 섹터, DCF, 시총 일괄 조회 (1 req)"""
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
    """FMP 스크리너 + 프로필을 30분 캐시로 관리. (screener, profile_map) 반환"""
    now = time.time()
    if _fmp_cache["ts"] and now - _fmp_cache["ts"] < _CACHE_FMP_TTL:
        return _fmp_cache["screener"], _fmp_cache["profiles"]

    # 스크리너는 독립 호출, 프로필은 후보 심볼 기준
    syms = list({s["symbol"] for s in candidates})
    screener_raw, profiles = await asyncio.gather(
        _fetch_fmp_screener(10),
        _fetch_fmp_profiles(syms),
    )

    # 스크리너 결과를 Alpaca snapshot 형식으로 정규화
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


# ── Step 2: Massive.com 전일 거래량 ──────────────────────────────────────────

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


# ── Step 3: 스코어링 (FMP 펀더멘털 보너스 포함) ──────────────────────────────

def _score_stock(stock: dict, prev_vol_map: dict, fmp_map: dict) -> float:
    sym       = stock.get("symbol", "")
    today_vol = float(stock.get("volume", 0) or 0)
    prev_vol  = float(prev_vol_map.get(sym, 0) or 0)
    price     = float(stock.get("price", 0) or 0)
    chg_pct   = float(stock.get("percent_change", 0) or 0)

    # 거래량 급증 비율 (40점) — 전일 대비 3배 이상이면 만점
    if prev_vol > 0:
        vol_score = min(today_vol / prev_vol / 3.0, 1.0) * 40
    else:
        vol_score = 0.0

    # 등락률 적정성 (30점) — 이미 급등한 종목 배제
    if -1 <= chg_pct <= 3:
        chg_score = 30.0
    elif 3 < chg_pct <= 7:
        chg_score = 20.0
    elif 7 < chg_pct <= 10:
        chg_score = 10.0
    else:
        chg_score = 0.0

    # 유동성 (10점) — 거래대금 $1M 이상
    liq_score = 10.0 if today_vol * price >= 1_000_000 else 0.0

    # FMP 펀더멘털 보너스 (20점)
    fmp = fmp_map.get(sym, {})
    pe  = fmp.get("pe")
    sector_pe = _SECTOR_PE.get(fmp.get("sector", ""), 20.0)
    dcf = fmp.get("dcf")

    fundamental_score = 0.0
    if pe and pe > 0:
        if pe < sector_pe * 0.8:    # 섹터 평균 대비 20% 이상 저평가
            fundamental_score += 15.0
        elif pe < sector_pe:        # 섹터 평균보다 저평가
            fundamental_score += 8.0
    if dcf and price and dcf > price * 1.10:   # DCF 대비 10% 이상 내재가치 저평가
        fundamental_score += 5.0

    return vol_score + chg_score + liq_score + fundamental_score


# ── Step 4: Claude 분석 (실제 FMP 수치 주입) ─────────────────────────────────

async def _analyze(stocks: list[dict], fmp_map: dict) -> dict[str, dict]:  # pylint: disable=too-many-locals
    if not stocks:
        return {}

    lines = []
    for s in stocks:
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
            upside = (dcf - price) / price * 100
            dcf_str = f" DCF:${dcf:.0f}({upside:+.0f}%)"
        sec_str = f" [{sector}]" if sector else ""

        lines.append(
            f"{sym} ${price:.2f} {'+' if chg >= 0 else ''}{chg:.2f}%"
            f" 거래량{vol}K{pe_str}{dcf_str}{sec_str}"
        )

    syms   = ", ".join(s["symbol"] for s in stocks)
    prompt = (
        "미국 주식 데이터:\n" + "\n".join(lines) + "\n\n"
        f"각 종목({syms})을 분석해 JSON으로만 반환. 다른 텍스트 없이.\n"
        '{"SYM":{"reason":"주목이유25자이내한국어","risk":"위험20자이내또는null",'
        '"confidence":2,"analyst":"매수","growth":"+12%EPS(YoY)","buy_pick":true}}\n\n'
        "reason=거래량+펀더멘털 종합근거(제공된 PE/DCF 활용), "
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

def _normalize(raw: dict, category: str, reason_map: dict, fmp_map: dict) -> dict:
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

    return {
        "sym":        sym,
        "price":      round(price, 2),
        "change":     round(float(raw.get("change", 0)), 2),
        "chg_pct":    round(float(raw.get("percent_change", 0)), 2),
        "volume":     int(raw.get("volume", 0)),
        "category":   category,
        "reason":     info.get("reason", ""),
        "risk":       info.get("risk"),
        "confidence": info.get("confidence"),
        "pe":         round(pe_val, 1) if pe_val else None,
        "sector_pe":  sector_pe,
        "analyst":    info.get("analyst"),
        "growth":     info.get("growth"),
        "buy_pick":   bool(info.get("buy_pick", False)),
        "sector":     sector or None,
        "dcf":        round(dcf, 2) if dcf else None,
        "dcf_upside": round((dcf - price) / price * 100, 1) if dcf and price else None,
        "mkt_cap":    fmp.get("mktCap"),
    }


# ── 라우터 ────────────────────────────────────────────────────────────────────

@router.get("")
async def get_trending():  # pylint: disable=too-many-locals
    now = time.time()
    ttl = _CACHE_TTL_OPEN if _is_market_open() else _CACHE_TTL_CLOSED
    if _cache["data"] and now - _cache["ts"] < ttl:
        return _cache["data"]

    # Step 1a: Alpaca 후보군 수집 (확장)
    actives_raw, (gainers_raw, losers_raw) = await asyncio.gather(
        _fetch_most_actives(20),
        _fetch_movers(10),
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

    # FMP 스크리너 후보 병합 (Alpaca에 없는 종목만)
    alpaca_syms = {s["symbol"] for s in alpaca_candidates}
    fmp_screener_new = [
        s for s in fmp_screener
        if s["symbol"] not in alpaca_syms and s.get("price", 0) >= MIN_PRICE
    ]

    # FMP 후보의 프로필도 추가 조회 (캐시에 없는 경우)
    fmp_new_syms = [s["symbol"] for s in fmp_screener_new if s["symbol"] not in fmp_profiles]
    if fmp_new_syms:
        extra = await _fetch_fmp_profiles(fmp_new_syms)
        fmp_profiles.update(extra)

    all_candidates = alpaca_candidates + fmp_screener_new

    # Step 2: Massive 전일 거래량
    all_syms     = [s["symbol"] for s in all_candidates]
    prev_vol_map = await _fetch_prev_volumes_massive(all_syms)

    # Step 3: 스코어링 → 상위 10종목 (FMP 펀더멘털 보너스 반영)
    scored = sorted(
        all_candidates,
        key=lambda s: _score_stock(s, prev_vol_map, fmp_profiles),
        reverse=True,
    )
    top10 = scored[:10]

    # 카테고리 매핑
    gainer_syms    = {s["symbol"] for s in gainers_raw}
    fmp_screener_syms = {s["symbol"] for s in fmp_screener_new}
    def _category(sym: str) -> str:
        if sym in fmp_screener_syms:
            return "fmp_pick"
        if sym in active_syms:
            return "most_active"
        if sym in gainer_syms:
            return "gainer"
        return "loser"

    # Step 4: Claude 분석 (실제 FMP 수치 포함)
    reason_map = await _analyze(top10, fmp_profiles)

    all_normalized = [
        _normalize(s, _category(s["symbol"]), reason_map, fmp_profiles)
        for s in top10
    ]
    picks = [s for s in all_normalized if s["buy_pick"]]

    result = {"picks": picks}
    _cache["data"] = result
    _cache["ts"]   = now
    return result
