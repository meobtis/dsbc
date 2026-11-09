import re
import unicodedata
from typing import List

ILLEGAL_FS_CHARS = re.compile(r'[/\\:*?"<>|]+')
EXTRA_WHITESPACE = re.compile(r'\s+')

# Matches double dandas / end of verses (e.g. || 1 || or ॥१२॥ or || or ॥)
VERSE_END_REGEX = re.compile(r'(\|\||\u0965)\s*(\d+|[०-९]+)?\s*(\|\||\u0965)?\s*$')

# Matches single danda or comma at end of line (half-verse / pāda)
# Uses negative lookbehind and lookahead to ensure it is not part of a double danda
HALF_VERSE_REGEX = re.compile(r'((?<!\|)\|(?!\s*\|)|(?<!\u0965)\u0964(?!\s*\u0965)|,)\s*$')


def sanitize_filename(name: str, max_length: int = 120) -> str:
    """Sanitize string for safe use in file/folder names across Mac/Linux/Windows.

    Preserves Devanagari and Sanskrit diacritics (IAST), while removing illegal filesystem
    characters.
    """
    if not name:
        return "untitled"
    # Unicode NFC normalization
    name = unicodedata.normalize("NFC", name)
    # Replace illegal filesystem chars
    name = ILLEGAL_FS_CHARS.sub("_", name)
    # Collapse whitespace
    name = EXTRA_WHITESPACE.sub(" ", name).strip(". ")
    if len(name) > max_length:
        name = name[:max_length].rstrip(". _")
    return name or "untitled"


def parse_category_path(raw_category: str) -> List[str]:
    """Parse 'Romanized » śāstrapiṭaka » abhidharma' into list of clean directory parts.

    Skips the root script element ('Romanized' or 'देवनागरी') since that is handled
    as the top-level directory.
    """
    if not raw_category:
        return ["uncategorized"]
    parts = [p.strip() for p in raw_category.split("»") if p.strip()]
    if not parts:
        return ["uncategorized"]
    # If the first part is 'Romanized' or 'देवनागरी', return the rest
    if parts[0].lower() in {"romanized", "देवनागरी"}:
        parts = parts[1:]
    return [sanitize_filename(p) for p in parts] if parts else ["general"]


def clean_sanskrit_text(raw_text: str) -> str:
    """Format Sanskrit text into clean Markdown.

    - Verse lines ending in single danda (| or ।) get two trailing spaces for Markdown hard breaks.
    - Verse ends ending in double danda (|| or ॥ with optional verse numbers) are followed by blank lines.
    - Normalizes unicode spaces and strips empty lines.
    """
    if not raw_text:
        return ""

    raw_text = raw_text.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = raw_text.split("\n")

    cleaned_input: List[str] = []
    for line in lines:
        stripped = line.strip()
        # Filter out DSBC boilerplate artifacts
        if stripped.lower() in {
            "end of title information",
            "technical details",
            "book links",
            "no data available.",
        }:
            continue
        if stripped:
            cleaned_input.append(stripped)

    formatted_lines: List[str] = []
    for line in cleaned_input:
        if VERSE_END_REGEX.search(line):
            formatted_lines.append(line)
            formatted_lines.append("")  # Blank line after full verse stanza
        elif HALF_VERSE_REGEX.search(line):
            formatted_lines.append(line + "  ")  # Hard break within verse
        else:
            # Prose line or prose paragraph
            formatted_lines.append(line)
            formatted_lines.append("")

    res = "\n".join(formatted_lines)
    # Collapse multiple blank lines
    res = re.sub(r"\n{3,}", "\n\n", res).strip()
    return res
