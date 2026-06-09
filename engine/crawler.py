"""Async HTTP crawler using aiohttp with rate limiting."""

import asyncio
import logging
from urllib.parse import urljoin, urlparse

import aiohttp

from shared.constants import REQUEST_DELAY, REQUEST_TIMEOUT, TARGET_URL, USER_AGENT

logger = logging.getLogger(__name__)


class CrawlerError(Exception):
    """Raised on non-200 responses, timeouts, or connection failures."""


def _is_internal(url: str) -> bool:
    """Return True if the URL belongs to the target domain."""
    return urlparse(url).netloc == urlparse(TARGET_URL).netloc


async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    """Fetch a single page and return its HTML. Raises CrawlerError on failure."""
    try:
        logger.debug("Fetching: %s", url)
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as resp:
            if resp.status != 200:
                raise CrawlerError(f"HTTP {resp.status} for {url}")
            html = await resp.text(errors="replace")
        await asyncio.sleep(REQUEST_DELAY)
        return html
    except aiohttp.ClientError as exc:
        raise CrawlerError(f"Connection error for {url}: {exc}") from exc
    except asyncio.TimeoutError as exc:
        raise CrawlerError(f"Timeout for {url}") from exc


def get_offer_links(html: str, base_url: str) -> list[str]:
    """Extract absolute /oferta/... links from a listing page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for tag in soup.find_all("a", href=True):
        href: str = tag["href"]
        if "/oferta/" in href:
            absolute = urljoin(base_url, href)
            if _is_internal(absolute) and absolute not in links:
                links.append(absolute)
    logger.debug("Found %d offer links on %s", len(links), base_url)
    return links


def get_next_page_url(html: str, base_url: str) -> str | None:
    """Extract the URL of the next pagination page, or None if last page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")

    # Kingdom Elblag uses rel="next" or an arrow/next-page link
    next_tag = soup.find("a", rel="next") or soup.find("a", string=lambda t: t and "następna" in t.lower())
    if next_tag and next_tag.get("href"):
        return urljoin(base_url, next_tag["href"])

    # Fallback: look for a pagination link with class containing 'next'
    next_tag = soup.find("a", class_=lambda c: c and "next" in c)
    if next_tag and next_tag.get("href"):
        return urljoin(base_url, next_tag["href"])

    return None


def build_session() -> aiohttp.ClientSession:
    """Create a shared aiohttp session with the project User-Agent."""
    headers = {"User-Agent": USER_AGENT}
    return aiohttp.ClientSession(headers=headers)
