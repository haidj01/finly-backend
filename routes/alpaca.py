import os
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/alpaca")

PAPER = "https://paper-api.alpaca.markets"
DATA  = "https://data.alpaca.markets"


def _headers():
    return {
        "APCA-API-KEY-ID":     os.environ["ALPACA_API_KEY"],
        "APCA-API-SECRET-KEY": os.environ["ALPACA_API_SECRET"],
    }


@router.get("/account")
async def get_account():
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(f"{PAPER}/v2/account", headers=_headers())
    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=res.text)
    return res.json()


@router.get("/positions")
async def get_positions():
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(f"{PAPER}/v2/positions", headers=_headers())
    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=res.text)
    return res.json()


@router.get("/prices")
async def get_prices(symbols: str):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(
            f"{DATA}/v2/stocks/trades/latest",
            params={"symbols": symbols, "feed": "iex"},
            headers=_headers(),
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
        res = await client.get(f"{DATA}/v2/assets/{sym}", headers=_headers())
    if res.status_code == 404:
        return None
    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=res.text)
    return res.json()


class OrderRequest(BaseModel):
    symbol: str
    qty: int
    side: str


@router.get("/orders")
async def get_orders(status: str = "all", limit: int = 20):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(
            f"{PAPER}/v2/orders",
            params={"status": status, "limit": limit, "direction": "desc"},
            headers=_headers(),
        )
    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=res.text)
    return res.json()


@router.post("/orders")
async def place_order(req: OrderRequest):
    if req.qty < 1 or req.qty > 10000:
        raise HTTPException(status_code=400, detail="수량은 1~10,000주 사이여야 합니다.")
    if req.side not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="side는 buy 또는 sell이어야 합니다.")

    body = {
        "symbol": req.symbol,
        "qty": req.qty,
        "side": req.side,
        "type": "market",
        "time_in_force": "day",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(f"{PAPER}/v2/orders", headers=_headers(), json=body)
    data = res.json()
    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=data.get("message", "주문 실패"))
    return data
