import os
from datetime import datetime, timedelta, timezone
import httpx
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/alpaca")

_AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8001")
DATA       = "https://data.alpaca.markets"


def _agent_headers() -> dict:
    token = os.getenv("FINLY_INTERNAL_TOKEN")
    return {"X-Internal-Token": token} if token else {}


def _data_headers():
    return {
        "APCA-API-KEY-ID":     os.environ["ALPACA_API_KEY"],
        "APCA-API-SECRET-KEY": os.environ["ALPACA_API_SECRET"],
    }


@router.get("/account")
async def get_account():
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(f"{_AGENT_URL}/api/alpaca/account", headers=_agent_headers())
    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=res.text)
    return res.json()


@router.get("/positions")
async def get_positions():
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(f"{_AGENT_URL}/api/alpaca/positions", headers=_agent_headers())
    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=res.text)
    return res.json()


@router.get("/prices")
async def get_prices(symbols: str):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(
            f"{DATA}/v2/stocks/trades/latest",
            params={"symbols": symbols, "feed": "iex"},
            headers=_data_headers(),
        )
    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=res.text)
    data = res.json()
    return {
        sym: round(t["p"], 2)
        for sym, t in (data.get("trades") or {}).items()
        if t.get("p")
    }


@router.get("/asset/{sym}")
async def get_asset(sym: str):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(f"{DATA}/v2/assets/{sym}", headers=_data_headers())
    if res.status_code == 404:
        return None
    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=res.text)
    return res.json()


@router.get("/snapshot/{sym}")
async def get_snapshot(sym: str):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(
            f"{DATA}/v2/stocks/snapshots",
            params={"symbols": sym.upper(), "feed": "iex"},
            headers=_data_headers(),
        )
    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=res.text)
    snap = res.json().get(sym.upper())
    if not snap:
        raise HTTPException(status_code=404, detail=f"{sym} 스냅샷 없음")
    return snap


_PERIOD_CFG = {
    "1D": {"timeframe": "1Hour", "days": 3},
    "1W": {"timeframe": "1Day",  "days": 7},
    "1M": {"timeframe": "1Day",  "days": 30},
    "1Y": {"timeframe": "1Day",  "days": 365},
}

@router.get("/bars/{sym}")
async def get_bars(sym: str, period: str = "1M"):
    cfg = _PERIOD_CFG.get(period, _PERIOD_CFG["1M"])
    start = (datetime.now(timezone.utc) - timedelta(days=cfg["days"])).strftime("%Y-%m-%d")
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(
            f"{DATA}/v2/stocks/{sym.upper()}/bars",
            params={"timeframe": cfg["timeframe"], "start": start,
                    "feed": "iex", "adjustment": "raw"},
            headers=_data_headers(),
        )
    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=res.text)
    return res.json().get("bars") or []


@router.get("/stats/{sym}")
async def get_stock_stats(sym: str):
    """52주 고가/저가 + 20일 평균 거래량 반환."""
    start = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(
            f"{DATA}/v2/stocks/{sym.upper()}/bars",
            params={"timeframe": "1Day", "start": start, "feed": "iex", "adjustment": "raw"},
            headers=_data_headers(),
        )
    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=res.text)
    bars = res.json().get("bars") or []
    if not bars:
        raise HTTPException(status_code=404, detail=f"{sym} 데이터 없음")
    highs   = [b["h"] for b in bars]
    lows    = [b["l"] for b in bars]
    volumes = [b["v"] for b in bars]
    avg_vol = sum(volumes[-20:]) / len(volumes[-20:]) if volumes else 0
    return {
        "week52_high": max(highs),
        "week52_low":  min(lows),
        "avg_vol_20d": round(avg_vol),
    }


@router.get("/orders")
async def get_orders(status: str = "all", limit: int = 20):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(
            f"{_AGENT_URL}/api/alpaca/orders",
            params={"status": status, "limit": limit},
            headers=_agent_headers(),
        )
    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=res.text)
    return res.json()


@router.post("/orders")
async def place_order(request: Request):
    body = await request.json()
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(f"{_AGENT_URL}/api/alpaca/orders", json=body, headers=_agent_headers())
    data = res.json()
    if res.status_code not in (200, 201):
        raise HTTPException(status_code=res.status_code, detail=data.get("detail", "주문 실패"))
    return data
