import os
import httpx
from fastapi import APIRouter, HTTPException, Request
from db import get_pool

router = APIRouter(prefix="/api/strategy")
_AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8001")


def _agent_headers() -> dict:
    token = os.getenv("FINLY_INTERNAL_TOKEN")
    return {"X-Internal-Token": token} if token else {}


@router.get("")
async def list_strategies():
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(f"{_AGENT_URL}/api/strategy", headers=_agent_headers())
    if res.status_code != 200:
        raise HTTPException(res.status_code, res.text)
    return res.json()


@router.post("")
async def create_strategy(request: Request):
    body = await request.json()
    symbol = (body.get("symbol") or "").upper().strip()
    if symbol:
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT symbol FROM watchlist WHERE symbol = $1 AND active = TRUE",
                    symbol,
                )
            if not row:
                raise HTTPException(
                    400,
                    f"{symbol}은(는) watchlist에 등록되지 않은 종목입니다. "
                    "먼저 watchlist에 추가하세요.",
                )
        except RuntimeError:
            pass  # DATABASE_URL 미설정 시 검증 스킵
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(f"{_AGENT_URL}/api/strategy", json=body, headers=_agent_headers())
    if res.status_code not in (200, 201):
        raise HTTPException(res.status_code, res.text)
    return res.json()


@router.patch("/{sid}/toggle")
async def toggle_strategy(sid: str):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.patch(f"{_AGENT_URL}/api/strategy/{sid}/toggle", headers=_agent_headers())
    if res.status_code != 200:
        raise HTTPException(res.status_code, res.text)
    return res.json()


@router.delete("/{sid}")
async def delete_strategy(sid: str):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.delete(f"{_AGENT_URL}/api/strategy/{sid}", headers=_agent_headers())
    if res.status_code != 200:
        raise HTTPException(res.status_code, res.text)
    return res.json()


@router.get("/trade-history")
async def get_trade_history(request: Request):
    params = dict(request.query_params)
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(f"{_AGENT_URL}/api/agent/trade-history", params=params, headers=_agent_headers())
    if res.status_code != 200:
        raise HTTPException(res.status_code, res.text)
    return res.json()


@router.get("/watchdog/status")
async def get_watchdog_status():
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(f"{_AGENT_URL}/api/agent/watchdog/status", headers=_agent_headers())
    if res.status_code != 200:
        raise HTTPException(res.status_code, res.text)
    return res.json()


@router.post("/watchdog/config")
async def update_watchdog_config(request: Request):
    body = await request.json()
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(f"{_AGENT_URL}/api/agent/watchdog/config", json=body, headers=_agent_headers())
    if res.status_code != 200:
        raise HTTPException(res.status_code, res.text)
    return res.json()


@router.get("/engine/status")
async def get_engine_status():
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(f"{_AGENT_URL}/api/agent/engine/status", headers=_agent_headers())
    if res.status_code != 200:
        raise HTTPException(res.status_code, res.text)
    return res.json()


@router.post("/engine/config")
async def update_engine_config(request: Request):
    body = await request.json()
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(f"{_AGENT_URL}/api/agent/engine/config", json=body, headers=_agent_headers())
    if res.status_code != 200:
        raise HTTPException(res.status_code, res.text)
    return res.json()


@router.get("/regime-recommendations")
async def get_regime_recommendations(request: Request):
    params = dict(request.query_params)
    async with httpx.AsyncClient(timeout=90) as client:
        res = await client.get(
            f"{_AGENT_URL}/api/agent/regime-recommendations",
            params=params,
            headers=_agent_headers(),
        )
    if res.status_code != 200:
        raise HTTPException(res.status_code, res.text)
    return res.json()
