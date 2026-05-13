import os
import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/market")
_AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8001")


@router.get("/regime")
async def get_market_regime():
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(f"{_AGENT_URL}/market/regime")
    if res.status_code != 200:
        raise HTTPException(res.status_code, res.text)
    return res.json()
