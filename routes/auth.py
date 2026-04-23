import os
import io
import base64
from datetime import datetime, timedelta

import pyotp
import qrcode
from fastapi import APIRouter, HTTPException
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth", tags=["auth"])

JWT_SECRET   = os.environ.get("JWT_SECRET", "change-this-secret-in-production")
ALGORITHM    = "HS256"
ACCESS_TTL   = 60 * 24   # 24시간 (분)
TEMP_TTL     = 5          # 임시 토큰 5분

ADMIN_USERNAME     = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
TOTP_SECRET        = os.environ.get("TOTP_SECRET", "")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class LoginRequest(BaseModel):
    username: str
    password: str


class MFAVerifyRequest(BaseModel):
    temp_token: str
    code: str


def _make_token(data: dict, expire_minutes: int) -> str:
    payload = {**data, "exp": datetime.utcnow() + timedelta(minutes=expire_minutes)}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="인증 토큰이 유효하지 않습니다.")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    return payload


@router.post("/login")
def login(req: LoginRequest):
    if not ADMIN_PASSWORD_HASH:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_PASSWORD_HASH 환경변수가 설정되지 않았습니다.",
        )
    if req.username != ADMIN_USERNAME or not pwd_context.verify(req.password, ADMIN_PASSWORD_HASH):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 틀렸습니다.")

    temp_token = _make_token({"sub": req.username, "type": "temp"}, TEMP_TTL)
    return {"requires_mfa": True, "temp_token": temp_token}


@router.post("/mfa/verify")
def mfa_verify(req: MFAVerifyRequest):
    if not TOTP_SECRET:
        raise HTTPException(status_code=503, detail="TOTP_SECRET이 설정되지 않았습니다. /api/auth/mfa/setup을 먼저 실행하세요.")

    try:
        payload = jwt.decode(req.temp_token, JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="임시 토큰이 만료되었거나 유효하지 않습니다.")

    if payload.get("type") != "temp":
        raise HTTPException(status_code=401, detail="Invalid token type")

    totp = pyotp.TOTP(TOTP_SECRET)
    if not totp.verify(req.code, valid_window=1):
        raise HTTPException(status_code=401, detail="인증 코드가 올바르지 않습니다.")

    access_token = _make_token({"sub": payload["sub"], "type": "access"}, ACCESS_TTL)
    return {"access_token": access_token, "token_type": "bearer", "expires_in": ACCESS_TTL * 60}


@router.get("/mfa/setup")
def mfa_setup():
    """최초 1회: TOTP 시크릿 + QR 코드 생성. TOTP_SECRET이 이미 설정된 경우 차단."""
    if TOTP_SECRET:
        raise HTTPException(status_code=400, detail="MFA가 이미 설정되어 있습니다.")

    secret = pyotp.random_base32()
    uri    = pyotp.TOTP(secret).provisioning_uri(name=ADMIN_USERNAME, issuer_name="Finly")

    buf = io.BytesIO()
    qrcode.make(uri).save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return {
        "secret":    secret,
        "qr_code":   f"data:image/png;base64,{qr_b64}",
        "next_step": f"1. Google Authenticator에서 QR 코드를 스캔하세요\n2. .env에 TOTP_SECRET={secret} 추가 후 서버를 재시작하세요",
    }
