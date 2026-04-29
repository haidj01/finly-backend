import os
import json
import re
import time
import asyncio
import httpx
from fastapi import APIRouter

router = APIRouter(prefix="/api/trending")

DATA           = "https://data.alpaca.markets"
_CACHE_TTL     = 300  # 5분
_cache: dict   = {"data": None, "ts": 0}
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL   = "claude-sonnet-4-6-20250514"


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
    """티커 목록의 snapshot(가격/등락률) 조회 → {sym: {price, change, percent_change}}"""
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
        for sym, data in res.json().items():
            daily = data.get("dailyBar", {})
            o, c = daily.get("o", 0), daily.get("c", 0)
            change = round(c - o, 4)
            pct = round((c - o) / o * 100, 2) if o else 0.0
            result[sym] = {"price": round(c, 2), "change": change, "percent_change": pct}
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


async def _analyze(stocks: list[dict]) -> dict[str, str]:
    """티커 목록을 Claude web_search로 분석 → {sym: reason} 반환"""
    if not stocks:
        return {}

    syms = ", ".join(s["symbol"] for s in stocks)
    prompt = (
        f"오늘 미국 주식시장에서 주목받는 다음 종목들을 웹검색으로 조사하고, "
        f"각 종목이 왜 주목받는지 한국어로 한 줄(30자 이내)로 설명해줘: {syms}\n\n"
        "JSON 객체만 반환해. 다른 텍스트 없이.\n"
        '형식: {"AAPL": "이유", "NVDA": "이유"}'
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
    sym = raw.get("symbol", "")
    return {
        "sym":     sym,
        "price":   round(float(raw.get("price", 0)), 2),
        "change":  round(float(raw.get("change", 0)), 2),
        "chg_pct": round(float(raw.get("percent_change", 0)), 2),
        "volume":  int(raw.get("volume", 0)),
        "category": category,
        "reason":  reason_map.get(sym, ""),
    }


@router.get("")
async def get_trending():
    now = time.time()
    if _cache["data"] and now - _cache["ts"] < _CACHE_TTL:
        return _cache["data"]

    actives_raw, (gainers_raw, losers_raw) = await asyncio.gather(
        _fetch_most_actives(8),
        _fetch_movers(5),
    )

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
