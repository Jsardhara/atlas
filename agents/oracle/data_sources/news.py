"""CryptoPanic + RSS news fetcher."""
import asyncio
import logging
from datetime import datetime, timedelta

import feedparser
import httpx

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://coindesk.com/arc/outboundfeeds/rss/",
    "https://decrypt.co/feed",
]


async def fetch_cryptopanic(api_key: str, pairs: list[str]) -> list[dict]:
    if not api_key:
        return []
    currencies = ",".join(p.split("/")[0] for p in pairs)
    url = f"https://cryptopanic.com/api/v1/posts/?auth_token={api_key}&currencies={currencies}&filter=important"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            data = resp.json()
            return [
                {"title": post["title"], "url": post["url"],
                 "published": post.get("published_at", ""), "source": "cryptopanic",
                 "votes": post.get("votes", {})}
                for post in data.get("results", [])[:15]
            ]
    except Exception as e:
        logger.warning("CryptoPanic fetch error: %s", e)
        return []


async def fetch_rss_headlines() -> list[dict]:
    headlines = []
    cutoff = datetime.utcnow() - timedelta(hours=6)

    async def fetch_feed(url: str):
        try:
            loop = asyncio.get_event_loop()
            feed = await loop.run_in_executor(None, feedparser.parse, url)
            for entry in feed.entries[:5]:
                headlines.append({
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", "")[:300],
                    "source": url.split("/")[2],
                    "published": entry.get("published", ""),
                })
        except Exception as e:
            logger.warning("RSS fetch error %s: %s", url, e)

    await asyncio.gather(*[fetch_feed(url) for url in RSS_FEEDS])
    return headlines


async def fetch_fear_and_greed() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get("https://api.alternative.me/fng/?limit=2")
            data = resp.json()
            latest = data["data"][0]
            return {
                "value": int(latest["value"]),
                "classification": latest["value_classification"],
                "timestamp": latest["timestamp"],
            }
    except Exception as e:
        logger.warning("Fear & Greed fetch error: %s", e)
        return {"value": 50, "classification": "Neutral"}
