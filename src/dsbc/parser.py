import re
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup

from .utils import clean_sanskrit_text


def parse_master_list(html: str, script_name: str) -> List[Dict[str, Any]]:
    """Parse the browse-by-list HTML table into a list of book dictionaries."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return []

    books = []
    rows = table.find_all("tr")[1:]  # Skip header
    for r in rows:
        tds = r.find_all("td")
        if len(tds) < 2:
            continue
        link = tds[0].find("a")
        if not link:
            continue

        book_url = link.get("href", "").strip()
        book_title = link.get_text(strip=True)

        # Extract book ID from URL (e.g. /canon-text/book/800)
        m = re.search(r"/book/(\d+)", book_url)
        book_id = int(m.group(1)) if m else None

        category_path = tds[1].get_text(strip=True)

        books.append({
            "book_id": book_id,
            "title": book_title,
            "book_url": book_url,
            "category_path": category_path,
            "script": script_name,
        })

    return books


def parse_book_page(html: str) -> Dict[str, Any]:
    """Parse a /canon-text/book/<id> page to extract metadata and chapter/content links."""
    soup = BeautifulSoup(html, "html.parser")

    # Title
    title_el = soup.find("h3", class_="abour")
    title = title_el.get_text(strip=True) if title_el else ""

    # Bibliographic info in title-info
    biblio: Dict[str, str] = {}
    ti = soup.find("div", class_="title-info")
    if ti:
        for li in ti.find_all("li"):
            week = li.find("span", class_="week")
            hours = li.find("div", class_="hours") or li.find("a")
            if week and hours:
                k = week.get_text(strip=True).rstrip(":")
                v = hours.get_text(strip=True)
                if k:
                    biblio[k] = v

    # Chapters table
    chapters = []
    table = soup.find("table")
    if table:
        for tr in table.find_all("tr")[1:]:
            tds = tr.find_all("td")
            if len(tds) >= 2:
                a = tds[1].find("a")
                if a:
                    sn = tds[0].get_text(strip=True)
                    ch_title = a.get_text(strip=True)
                    ch_url = a.get("href", "").strip()
                    m = re.search(r"/content/(\d+)/(\d+)", ch_url)
                    content_id = int(m.group(2)) if m else None
                    chapters.append({
                        "sn": sn,
                        "title": ch_title,
                        "url": ch_url,
                        "content_id": content_id,
                    })

    return {
        "title": title,
        "bibliography": biblio,
        "chapters": chapters,
    }


def parse_content_page(html: str) -> Dict[str, Any]:
    """Parse a /canon-text/content/<book_id>/<content_id> page."""
    soup = BeautifulSoup(html, "html.parser")
    ns = soup.find("div", class_="news-section")
    if not ns:
        return {
            "title": "",
            "technical_details": {},
            "text": "",
        }

    # Chapter / section title
    title_el = ns.find("h3", class_="abour")
    title = title_el.get_text(strip=True) if title_el else ""

    # Technical details
    tech_details: Dict[str, str] = {}
    ti = ns.find("div", class_="title-info")
    if ti:
        for li in ti.find_all("li"):
            week = li.find("span", class_="week")
            hours = li.find("div", class_="hours") or li.find("a")
            if week and hours:
                k = week.get_text(strip=True).rstrip(":")
                # Clean up newlines or extra spaces in field labels
                k = re.sub(r"\s+", " ", k)
                v = hours.get_text(strip=True)
                if k:
                    tech_details[k] = v

    # Extract text:
    # First remove header chrome: breadcrumbs, title, technical details header, title-info
    for el in ns.find_all(["ul", "h3", "h5", "div"]):
        el.extract()

    raw_html = str(ns)
    # Replace <br/> and closing </p> with newlines to ensure proper spacing
    normalized_html = re.sub(r"<\s*br\s*/?>", "\n", raw_html, flags=re.I)
    normalized_html = re.sub(r"</p>", "\n\n", normalized_html, flags=re.I)

    soup2 = BeautifulSoup(normalized_html, "html.parser")
    raw_text = soup2.get_text()

    formatted_text = clean_sanskrit_text(raw_text)

    return {
        "title": title,
        "technical_details": tech_details,
        "text": formatted_text,
    }
