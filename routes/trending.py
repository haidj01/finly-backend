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
CLAUDE_API_URL    = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL      = "claude-sonnet-4-6-20250514"
MIN_PRICE         = 5.0   # 페니 스톡 제외 기준
_CACHE_TTL_OPEN   = 300   # 장중 5분
_CACHE_TTL_CLOSED = 3600  # 장 마감 1시간
_cache: dict      = {"data": None, "ts": 0}


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


async def _fetch_snapshots(symbols: list[str]) -> dict[str, dict]:
    """
    티커 목록의 snapshot(가격/등락률) 조회 → {sym: {price, change, percent_change}}

    가격 산정 우선순위:
    - 장중(09:30~16:00 ET): latestTrade.p > minuteBar.c > dailyBar.c
    - 장외: dailyBar.c > latestTrade.p

    등락률: 항상 prevDailyBar.c(전일 종가) 기준으로 계산
    """
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
        is_market_open = _is_market_open()

        for sym, data in res.json().items():
            # 가격 결정: 장중/장외 우선순위에 따라 결정
            price = 0.0
            if is_market_open:
                # 장중: latestTrade.p > minuteBar.c > dailyBar.c
                latest_trade = data.get("latestTrade", {})
                if latest_trade.get("p"):
                    price = latest_trade.get("p", 0)
                else:
                    minute_bar = data.get("minuteBar", {})
                    if minute_bar.get("c"):
                        price = minute_bar.get("c", 0)
                    else:
                        daily_bar = data.get("dailyBar", {})
                        price = daily_bar.get("c", 0)
            else:
                # 장외: dailyBar.c > latestTrade.p
                daily_bar = data.get("dailyBar", {})
                if daily_bar.get("c"):
                    price = daily_bar.get("c", 0)
                else:
                    latest_trade = data.get("latestTrade", {})
                    price = latest_trade.get("p", 0)

            # 등락률 계산: 전일 종가 기준 (prevDailyBar.c)
            prev_close = data.get("prevDailyBar", {}).get("c", 0)
            change = round(price - prev_close, 4) if prev_close else 0.0
            pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0.0

            result[sym] = {
                "price": round(price, 2),
                "change": change,
                "percent_change": pct,
            }
        return result
    except Exception as e:
        print(f"[Alpaca snapshots] 예외: {e}")
        return {}


async def _fetch_most_actives(top: int = 8) -> list[dict]:
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
        s["price"]           = snap.get("price", 0)
        s["change"]          = snap.get("change", 0)
        s["percent_change"]  = snap.get("percent_change", 0)
    return actives


async def _fetch_movers(top: int = 5) -> tuple[list[dict], list[dict]]:
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


async def _analyze(stocks: list[dict]) -> dict[str, dict]:
    """티커 목록을 Claude web_search로 분석 → {sym: {reason, pe, analyst, growth, grade}} 반환"""
    if not stocks:
        return {}

    stock_lines = "\n".join(
        f"- {s['symbol']}: ${s.get('price', 0):.2f}, "
        f"{'+' if s.get('percent_change', 0) >= 0 else ''}{s.get('percent_change', 0):.2f}%, "
        f"거래량 {int(s.get('volume', 0)):,}"
        for s in stocks
    )
    prompt = (
        f"오늘 미국 주식시장 주목 종목 데이터입니다:\n{stock_lines}\n\n"
        "각 종목을 웹검색으로 조사해서 아래 JSON 형식으로만 반환해. 다른 텍스트 없이.\n\n"
        "{\n"
        '  "TICKER": {\n'
        '    "reason": "오늘 주목받는 핵심 이유 (30자 이내, 한국어)",\n'
        '    "pe": 28.5,\n'
        '    "analyst": "매수",\n'
        '    "growth": "+12%",\n'
        '    "grade": "B"\n'
        "  }\n"
        "}\n\n"
        "필드 설명:\n"
        "- pe: 현재 PER 숫자 (없으면 null)\n"
        "- analyst: 애널리스트 컨센서스 매수/중립/매도 (없으면 null)\n"
        "- growth: 최근 분기 매출 또는 EPS 성장률 예: +12% (없으면 null)\n"
        "- grade: 펀더멘털 종합 평가 A(우수)/B(양호)/C(보통)/D(취약) (필수)"
    )
    body = {
        "model":   CLAUDE_MODEL,
        "max_tokens": 2048,
        "tools":   [{"type": "web_search_20250305", "name": "web_search"}],
        "messages": [{"role": "user", "content": prompt}],
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


def _normalize(raw: dict, category: str, reason_map: dict) -> dict:
    sym  = raw.get("symbol", "")
    info = reason_map.get(sym) or {}
    if not isinstance(info, dict):
        info = {"reason": str(info)}
    return {
        "sym":      sym,
        "price":    round(float(raw.get("price", 0)), 2),
        "change":   round(float(raw.get("change", 0)), 2),
        "chg_pct":  round(float(raw.get("percent_change", 0)), 2),
        "volume":   int(raw.get("volume", 0)),
        "category": category,
        "reason":   info.get("reason", ""),
        "pe":       info.get("pe"),
        "analyst":  info.get("analyst"),
        "growth":   info.get("growth"),
        "grade":    info.get("grade"),
    }


@router.get("")
async def get_trending():
    now = time.time()
    ttl = _CACHE_TTL_OPEN if _is_market_open() else _CACHE_TTL_CLOSED
    if _cache["data"] and now - _cache["ts"] < ttl:
        return _cache["data"]

    actives_raw, (gainers_raw, losers_raw) = await asyncio.gather(
        _fetch_most_actives(8),
        _fetch_movers(5),
    )

    # 페니 스톡 제외 ($5 미만)
    actives_raw = [s for s in actives_raw if s.get("price", 0) >= MIN_PRICE]
    gainers_raw = [s for s in gainers_raw if s.get("price", 0) >= MIN_PRICE]
    losers_raw  = [s for s in losers_raw  if s.get("price", 0) >= MIN_PRICE]

    # actives에 이미 포함된 종목을 gainers/losers에서 제거
    active_syms = {s["symbol"] for s in actives_raw}
    gainers_raw = [s for s in gainers_raw if s["symbol"] not in active_syms]
    losers_raw  = [s for s in losers_raw  if s["symbol"] not in active_syms]

    # Claude 분석 대상 추출 (최대 15개)
    all_stocks = {s["symbol"]: s for s in actives_raw + gainers_raw + losers_raw}
    reason_map = await _analyze(list(all_stocks.values())[:15])

    result = {
        "actives": [_normalize(s, "most_active", reason_map) for s in actives_raw],
        "gainers": [_normalize(s, "gainer",      reason_map) for s in gainers_raw],
        "losers":  [_normalize(s, "loser",        reason_map) for s in losers_raw],
    }
    _cache["data"] = result
    _cache["ts"]   = now
    return result
