import os
import asyncpg

_pool = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL 환경변수가 설정되지 않았습니다.")
        _pool = await asyncpg.create_pool(url, min_size=2, max_size=10)
    return _pool


async def init_db() -> None:
    try:
        pool = await get_pool()
    except RuntimeError:
        return  # DATABASE_URL 미설정 시 무시 (로컬 개발용)
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                symbol       VARCHAR(10)  PRIMARY KEY,
                company_name VARCHAR(100) NOT NULL DEFAULT '',
                active       BOOLEAN      NOT NULL DEFAULT TRUE,
                added_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                modified_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
            )
        """)
