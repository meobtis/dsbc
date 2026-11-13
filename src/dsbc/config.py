from pathlib import Path

BASE_URL = "https://www.dsbcproject.org"
ROMANIZED_LIST_URL = f"{BASE_URL}/canon-text/browse-by-list/1"
DEVANAGARI_LIST_URL = f"{BASE_URL}/canon-text/browse-by-list/77"

# Default paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_BOOKS_DIR = RAW_DIR / "books"
RAW_CONTENT_DIR = RAW_DIR / "content"
MANIFEST_PATH = DATA_DIR / "manifest.json"
TEXTS_DIR = PROJECT_ROOT / "texts"
TRANSLITERATE_PATH = DATA_DIR / "transliterate.json"

# Request headers to simulate browser
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Network defaults
DEFAULT_CONCURRENCY = 8
DEFAULT_TIMEOUT = 25.0
DEFAULT_MAX_RETRIES = 4
