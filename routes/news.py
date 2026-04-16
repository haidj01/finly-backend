import os
import json
import re
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/news")

DATA           = "https://data.alpaca.markets"
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL   = "claude-sonnet-4-20250514"


def _alpaca_headers():
    return {
        "APCA-API-KEY-ID":     os.environ["ALPACA_API_KEY"],
        "APCA-API-SECRET-KEY": os.environ["ALPACA_API_SECRET"],
    }


def _claude_headers():
    return {
        "Content-Type":      "application/json",
        "x-api-key":         os.environ["CLAUDE_API_KEY"],
        "anthropic-version": "2023-06-01",
    }


def _one_week_ago() -> datetime:
    return datetime.now(timezone.utc) - timedelta(weeks=1)


# ── Alpaca ──────────────────────────────────────────────────────────────────

async def _fetch_alpaca_news(symbols: list[str], limit: int) -> tuple[list[dict], str | None]:
    start = _one_week_ago().strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(
                f"{DATA}/v1beta1/news",
                params={"symbols": ",".join(symbols), "limit": limit, "sort": "desc", "start": start},
                headers=_alpaca_headers(),
            )
        if res.status_code != 200:
            return [], f"Alpaca 뉴스 조회 실패 ({res.status_code})"

        items = []
        for n in res.json().get("news", []):
            sym = (n.get("symbols") or symbols[:1])[0]
            items.append({
                "sym":    sym,
                "hl":     n["headline"],
                "url":    n.get("url", ""),
                "time":   n["created_at"],
                "source": n.get("source", ""),
            })
        return items, None
    except Exception as e:
        return [], str(e)


# ── Google News RSS ──────────────────────────────────────────────────────────

async def _fetch_google_news(symbols: list[str], limit: int) -> tuple[list[dict], str | None]:
    query = " OR ".join(symbols) + " stock"
    url   = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            res = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})

        if res.status_code != 200:
            return [], f"Google News RSS 차단됨 ({res.status_code})"

        root    = ET.fromstring(res.content)
        channel = root.find("channel")
        if channel is None:
            return [], "Google News RSS 파싱 실패"

        cutoff = _one_week_ago()
        items  = []
        for item in channel.findall("item"):
            if len(items) >= limit:
                break
            title      = item.findtext("title", "")
            link       = item.findtext("link", "")
            pub_raw    = item.findtext("pubDate", "")
            source_el  = item.find("source")
            source     = source_el.text if source_el is not None else ""

            try:
                pub_dt = parsedate_to_datetime(pub_raw)
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue
                time_iso = pub_dt.isoformat()
            except Exception:
                time_iso = datetime.now(timezone.utc).isoformat()

            items.append({"hl": title, "url": link, "time": time_iso, "source": source})

        return items, None
    except Exception as e:
        return [], f"Google News RSS 차단됨: {e}"


# ── Claude: 번역 + 감성 분석 (1회 호출) ────────────────────────────────────

async def _analyze_and_translate(headlines: list[dict]) -> dict[int, dict]:
    if not headlines:
        return {}

    lines  = "\n".join(f'{h["id"]}. {h["headline"]}' for h in headlines)
    prompt = (
        "다음 미국 주식 뉴스 헤드라인들을 처리해줘.\n"
        "각 항목에 대해: (1) 한국어로 번역, (2) 주식 시장 감성을 bull/bear/neu 중 하나로 분류.\n"
        "JSON 배열만 반환해. 다른 텍스트 없이.\n"
        '형식: [{"id":<번호>,"hl_ko":"한국어 번역","sent":"bull|bear|neu"}]\n\n'
        f"{lines}"
    )
    body = {
        "model":     CLAUDE_MODEL,
        "max_tokens": 1024,
        "messages":  [{"role": "user", "content": prompt}],
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(CLAUDE_API_URL, headers=_claude_headers(), json=body)
        if res.status_code != 200:
            print(f"[Claude] 번역 실패 {res.status_code}: {res.text[:200]}")
            return {}
        text  = next((b["text"] for b in res.json().get("content", []) if b["type"] == "text"), "[]")
        match = re.search(r"\[.*\]", text, re.DOTALL)
        items = json.loads(match.group() if match else "[]")
        return {item["id"]: {"hl_ko": item.get("hl_ko", ""), "sent": item.get("sent", "neu")} for item in items}
    except Exception as e:
        print(f"[Claude] 번역 예외: {e}")
        return {}


# ── 엔드포인트 ───────────────────────────────────────────────────────────────

@router.get("")
async def get_news(symbols: str, limit: int = 10):
    sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        raise HTTPException(status_code=400, detail="symbols가 필요합니다.")

    # Alpaca + Google 동시 조회
    (alpaca_items, alpaca_err), (google_items, google_err) = await asyncio.gather(
        _fetch_alpaca_news(sym_list, limit),
        _fetch_google_news(sym_list, limit),
    )

    # 전체 헤드라인 모아서 Claude 1회 호출
    alpaca_cnt = len(alpaca_items)
    all_headlines = (
        [{"id": i + 1,              "headline": n["hl"]} for i, n in enumerate(alpaca_items)] +
        [{"id": alpaca_cnt + i + 1, "headline": n["hl"]} for i, n in enumerate(google_items)]
    )
    analysis = await _analyze_and_translate(all_headlines)

    def enrich(items: list[dict], offset: int) -> list[dict]:
        result = []
        for i, n in enumerate(items):
            info = analysis.get(offset + i + 1, {})
            result.append({
                "sym":    n.get("sym", sym_list[0]),
                "hl":     n["hl"],
                "hl_ko":  info.get("hl_ko") or n["hl"],
                "url":    n.get("url", ""),
                "time":   n["time"],
                "sent":   info.get("sent", "neu"),
                "source": n.get("source", ""),
            })
        return sorted(result, key=lambda x: x["time"], reverse=True)

    return {
        "alpaca": {"ok": alpaca_err is None, "error": alpaca_err, "items": enrich(alpaca_items, 0)},
        "google": {"ok": google_err is None, "error": google_err, "items": enrich(google_items, alpaca_cnt)},
    }
