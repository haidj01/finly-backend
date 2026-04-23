import os
import pathlib
import httpx
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import jwt, JWTError

from routes.claude   import router as claude_router
from routes.alpaca   import router as alpaca_router
from routes.news     import router as news_router
from routes.trending import router as trending_router
from routes.auth     import router as auth_router

app = FastAPI(title="Finly Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
)

_JWT_SECRET = os.environ.get("JWT_SECRET", "change-this-secret-in-production")
_PUBLIC_PATHS = {
    "/health",
    "/api/version",
    "/api/auth/login",
    "/api/auth/mfa/verify",
    "/api/auth/mfa/setup",
    "/docs",
    "/openapi.json",
    "/redoc",
}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS" or request.url.path in _PUBLIC_PATHS:
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "인증이 필요합니다."})

    token = auth_header[len("Bearer "):].strip()
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "access":
            return JSONResponse(status_code=401, content={"detail": "Invalid token type"})
    except JWTError:
        return JSONResponse(status_code=401, content={"detail": "인증 토큰이 유효하지 않습니다."})

    return await call_next(request)


app.include_router(auth_router)
app.include_router(claude_router)
app.include_router(alpaca_router)
app.include_router(news_router)
app.include_router(trending_router)


@app.get("/health")
def health():
    return {"status": "ok"}


_AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8001")


@app.get("/api/version")
async def version():
    v = (pathlib.Path(__file__).parent / "version.txt").read_text().strip()
    agent_version = "N/A"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{_AGENT_URL}/version", timeout=2.0)
            agent_version = r.json().get("version", "N/A")
    except Exception:
        pass
    return {"service": "finly-backend", "version": v, "agent_version": agent_version}
