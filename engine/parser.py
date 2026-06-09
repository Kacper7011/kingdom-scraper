"""HTML parser using BeautifulSoup4 for kingdomelblag.pl."""

import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from shared.models import Address, Contact, Offer

logger = logging.getLogger(__name__)


class ParserError(Exception):
    """Raised when mandatory fields cannot be extracted from HTML."""


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _extract_offer_id(url: str) -> str | None:
    """Pull the numeric ID segment from /oferta/<id>/... URLs."""
    match = re.search(r"/oferta/([^/]+)", url)
    return match.group(1) if match else None


def _parse_price(soup: BeautifulSoup) -> float | None:
    tag = soup.find("p", class_="price")
    if not tag:
        return None
    amount = tag.find("span", class_="amout")
    if not amount:
        return None
    raw = re.sub(r"[^\d,\.]", "", amount.get_text())
    raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_area(soup: BeautifulSoup) -> float | None:
    for div in soup.find_all("div", class_="area"):
        text = div.get_text(" ", strip=True)
        if "Powierzchnia" in text:
            match = re.search(r"([\d,\.]+)\s*m", text)
            if match:
                try:
                    return float(match.group(1).replace(",", "."))
                except ValueError:
                    pass
    return None


def _parse_images(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Return absolute URLs of all offer photo <img> tags (excludes logo/icons)."""
    urls: list[str] = []
    for img in soup.find_all("img", src=re.compile(r"/photos/")):
        absolute = urljoin(base_url, img["src"])
        if absolute not in urls:
            urls.append(absolute)
    return urls


def _parse_rooms(soup: BeautifulSoup) -> int | None:
    for div in soup.find_all("div", class_="area"):
        text = div.get_text(" ", strip=True)
        if "pokoi" in text.lower() or "pokoje" in text.lower():
            match = re.search(r"(\d+)", text)
            if match:
                return int(match.group(1))
    return None


def _parse_address_from_offer(soup: BeautifulSoup) -> Address:
    """Extract address from the h6 location line on a listing card or offer header."""
    tag = soup.find("h6", string=re.compile(r"warmi", re.I))
    if not tag:
        tag = soup.find("h6")
    if tag:
        parts = [p.strip() for p in tag.get_text(separator=",").split(",") if p.strip()]
        # typical: "warmińsko-mazurskie, Elbląg, Ulica"
        city = parts[1] if len(parts) > 1 else (parts[0] if parts else "")
        street = parts[2] if len(parts) > 2 else None
        region = parts[0] if parts else None
        return Address(city=city, street=street, region=region)

    # fallback: og:title contains "Miasto, Ulica, ..."
    meta = soup.find("meta", property="og:title")
    if meta:
        content = meta.get("content", "")
        parts = [p.strip() for p in content.split(",")]
        city = parts[0] if parts else ""
        street = parts[1] if len(parts) > 1 else None
        return Address(city=city, street=street, region="warmińsko-mazurskie")

    return Address(city="Elbląg", region="warmińsko-mazurskie")


def _classify_from_url(url: str) -> tuple[str, str]:
    """Derive category and transaction from the URL path segment."""
    path = urlparse(url).path.lower()

    category_map = {
        "mieszkan": "mieszkanie",
        "dom": "dom",
        "dzialk": "dzialka",
        "lokal": "lokal",
    }
    transaction_map = {
        "sprzedaz": "sprzedaz",
        "wynajem": "wynajem",
        "dzierzawa": "dzierzawa",
    }

    category = next((v for k, v in category_map.items() if k in path), "inne")
    transaction = next((v for k, v in transaction_map.items() if k in path), "sprzedaz")
    return category, transaction


def parse_offer(html: str, url: str) -> Offer | None:
    """Parse a single offer page into an Offer dataclass. Returns None on failure."""
    try:
        soup = _soup(html)
        offer_id = _extract_offer_id(url)
        if not offer_id:
            logger.warning("Cannot extract offer_id from %s", url)
            return None

        title_tag = soup.find("h2")
        title = title_tag.get_text(strip=True) if title_tag else ""
        if not title:
            meta = soup.find("meta", property="og:title")
            title = meta.get("content", "") if meta else ""

        category, transaction = _classify_from_url(url)
        address = _parse_address_from_offer(soup)
        price = _parse_price(soup)
        area = _parse_area(soup)
        rooms = _parse_rooms(soup)
        images = _parse_images(soup, url)

        logger.debug("Parsed offer %s: %s | %s %s | %d image(s)", offer_id, title, category, transaction, len(images))
        return Offer(
            offer_id=offer_id,
            title=title,
            category=category,
            transaction=transaction,
            url=url,
            address=address,
            price=price,
            area_m2=area,
            rooms=rooms,
            images=images,
        )
    except Exception as exc:
        logger.error("parse_offer failed for %s: %s", url, exc)
        return None


def parse_contact(html: str) -> Contact | None:
    """Extract office contact details from footer present on every page."""
    try:
        soup = _soup(html)

        name_tag = soup.find("p", class_="company")
        name = name_tag.get_text(strip=True) if name_tag else "Kingdom Nieruchomości"

        email_tag = soup.find("a", href=re.compile(r"^mailto:"))
        email = email_tag["href"].replace("mailto:", "").strip() if email_tag else ""

        phone_tag = soup.find("a", href=re.compile(r"^tel:"))
        phone = phone_tag.get_text(strip=True) if phone_tag else ""

        # address is in the <p> next to the location icon in widget_logo
        addr = ""
        for widget in soup.find_all("div", class_="widget_logo"):
            p = widget.find("p", string=re.compile(r"ul\.|Ogólna|Elbl", re.I))
            if not p:
                p = widget.find("p")
            if p and "fa-location" not in str(p):
                text = p.get_text(strip=True)
                if text and len(text) > 5:
                    addr = text
                    break

        if not email and not phone:
            logger.warning("parse_contact: no email or phone found")
            return None

        return Contact(name=name, email=email, phone=phone, address=addr)
    except Exception as exc:
        logger.error("parse_contact failed: %s", exc)
        return None


def parse_listing_urls(html: str, base_url: str) -> list[str]:
    """Return all absolute offer URLs found on a listing/category page."""
    soup = _soup(html)
    urls: list[str] = []
    for tag in soup.find_all("a", href=True):
        href: str = tag["href"]
        if "/oferta/" in href:
            absolute = urljoin(base_url, href)
            if absolute not in urls:
                urls.append(absolute)
    logger.debug("parse_listing_urls: found %d offers on %s", len(urls), base_url)
    return urls
