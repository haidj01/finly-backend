from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from db import get_pool

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistAddRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=10)
    company_name: str = Field("", max_length=100)


@router.get("")
async def list_watchlist():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT symbol, company_name, added_at, modified_at "
            "FROM watchlist WHERE active = TRUE ORDER BY added_at"
        )
    return [dict(r) for r in rows]


@router.post("", status_code=201)
async def add_watchlist(req: WatchlistAddRequest):
    symbol = req.symbol.upper().strip()
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO watchlist (symbol, company_name)
            VALUES ($1, $2)
            ON CONFLICT (symbol) DO UPDATE
              SET active       = TRUE,
                  company_name = EXCLUDED.company_name,
                  modified_at  = NOW()
            RETURNING symbol, company_name, active, added_at, modified_at
        """, symbol, req.company_name)
    return dict(row)


@router.delete("/{symbol}")
async def remove_watchlist(symbol: str):
    symbol = symbol.upper()
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE watchlist SET active = FALSE, modified_at = NOW() "
            "WHERE symbol = $1 AND active = TRUE",
            symbol,
        )
    if result == "UPDATE 0":
        raise HTTPException(404, "종목을 찾을 수 없습니다.")
    return {"message": f"{symbol} 삭제 완료"}
