import os
import httpx
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/strategy")
_AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8001")


@router.get("")
async def list_strategies():
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(f"{_AGENT_URL}/api/strategy")
    if res.status_code != 200:
        raise HTTPException(res.status_code, res.text)
    return res.json()


@router.post("")
async def create_strategy(request: Request):
    body = await request.json()
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(f"{_AGENT_URL}/api/strategy", json=body)
    if res.status_code not in (200, 201):
        raise HTTPException(res.status_code, res.text)
    return res.json()


@router.patch("/{sid}/toggle")
async def toggle_strategy(sid: str):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.patch(f"{_AGENT_URL}/api/strategy/{sid}/toggle")
    if res.status_code != 200:
        raise HTTPException(res.status_code, res.text)
    return res.json()


@router.delete("/{sid}")
async def delete_strategy(sid: str):
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.delete(f"{_AGENT_URL}/api/strategy/{sid}")
    if res.status_code != 200:
        raise HTTPException(res.status_code, res.text)
    return res.json()
