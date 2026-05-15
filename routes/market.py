import os
import httpx
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/market")
_AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8001")


def _agent_headers() -> dict:
    token = os.getenv("FINLY_INTERNAL_TOKEN")
    return {"X-Internal-Token": token} if token else {}


@router.get("/regime")
async def get_market_regime():
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(f"{_AGENT_URL}/market/regime", headers=_agent_headers())
    if res.status_code != 200:
        raise HTTPException(res.status_code, res.text)
    return res.json()


@router.get("/trading-mode")
async def get_trading_mode():
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(f"{_AGENT_URL}/market/trading-mode", headers=_agent_headers())
    if res.status_code != 200:
        raise HTTPException(res.status_code, res.text)
    return res.json()


@router.put("/trading-mode")
async def update_trading_mode(request: Request):
    body = await request.json()
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.put(f"{_AGENT_URL}/market/trading-mode", json=body, headers=_agent_headers())
    if res.status_code != 200:
        raise HTTPException(res.status_code, res.text)
    return res.json()
