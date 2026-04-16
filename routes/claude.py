import os
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/claude")

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL   = "claude-sonnet-4-20250514"

def _headers():
    return {
        "Content-Type": "application/json",
        "x-api-key": os.environ["CLAUDE_API_KEY"],
        "anthropic-version": "2023-06-01",
    }


class Message(BaseModel):
    role: str
    content: str | list


class ChatRequest(BaseModel):
    messages: list[Message]
    system: str


class TickerRequest(BaseModel):
    query: str


class SignalsRequest(BaseModel):
    symbols: list[str]


@router.post("/chat")
async def chat(req: ChatRequest):
    body = {
        "model": CLAUDE_MODEL,
        "max_tokens": 1024,
        "system": req.system,
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "messages": [m.model_dump() for m in req.messages],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(CLAUDE_API_URL, headers=_headers(), json=body)
    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=res.json())
    return res.json()


@router.post("/signals")
async def get_signals(req: SignalsRequest):
    if not req.symbols:
        raise HTTPException(status_code=400, detail="symbols는 비어있을 수 없습니다.")

    syms = ", ".join(req.symbols[:10])  # 최대 10개
    prompt = (
        f"다음 미국 주식 종목들을 웹검색으로 최신 시황·뉴스·기술적 지표를 확인한 뒤 "
        f"매매 신호를 분석해줘: {syms}\n\n"
        f"반드시 아래 JSON 배열 형식만 반환해. 다른 텍스트는 절대 포함하지 마.\n"
        f'[{{"type":"buy|sell|hold","sym":"티커","reason":"근거 30자 이내","conf":"신뢰도 XX%"}}]'
    )
    body = {
        "model": CLAUDE_MODEL,
        "max_tokens": 1024,
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "messages": [{"role": "user", "content": prompt}],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(CLAUDE_API_URL, headers=_headers(), json=body)
    if res.status_code != 200:
        err = res.json()
        msg = err.get("error", {}).get("message") or str(err)
        raise HTTPException(status_code=res.status_code, detail=msg)

    data = res.json()
    text = next((b["text"] for b in data.get("content", []) if b["type"] == "text"), "[]")

    import json, re
    match = re.search(r"\[.*\]", text, re.DOTALL)
    try:
        signals = json.loads(match.group() if match else "[]")
    except Exception:
        signals = []

    return signals


@router.post("/search-ticker")
async def search_ticker(req: TickerRequest):
    body = {
        "model": CLAUDE_MODEL,
        "max_tokens": 200,
        "messages": [{
            "role": "user",
            "content": f'"{req.query}"와 관련된 미국 상장 주식 티커를 최대 5개 찾아줘. JSON 배열만 반환해. 형식: [{{"sym":"AAPL","name":"Apple Inc."}},...] '
        }],
    }
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(CLAUDE_API_URL, headers=_headers(), json=body)
    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=res.json())
    return res.json()
