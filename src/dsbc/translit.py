"""Devanāgarī → IAST transliteration with Aksharamukha (https://www.aksharamukha.com/python).

Only characters of the Devanāgarī block are transliterated, so Markdown syntax, Latin text (such as
German or English notes), editorial marks and numbers outside Devanāgarī are left as they are.
The dandas ``।`` and ``॥`` are written ``|`` and ``||``, the convention of GRETIL and DSBC; Aksharamukha
would render them as ``.`` and ``..``.
"""

from __future__ import annotations

import re
import warnings
from importlib import metadata
from typing import List

# Devanāgarī, Devanāgarī Extended, Vedic Extensions and the joiners, without the dandas (U+0964, U+0965).
RUN = re.compile(r"[ऀ-ॣ०-ॿ᳐-᳹꣠-ꣿ‌‍]+")
CHUNK = 20000  # runs per call to Aksharamukha


def _process(text: str) -> str:
    with warnings.catch_warnings():
        # Aksharamukha 2.3 has invalid escape sequences in regular expressions that Python 3.12+ warns about.
        warnings.simplefilter("ignore", SyntaxWarning)
        from aksharamukha import transliterate
    return transliterate.process("Devanagari", "IAST", text)


def tool_version() -> str:
    return f"Aksharamukha {metadata.version('aksharamukha')}"


# The nukta is a typing artefact in Sanskrit texts: "गौड़" is gauḍa, "गाढ़" gāḍha, "स्फ़ुट" sphuṭa (Aksharamukha would
# read the last as "sfuṭa"). The precomposed letters U+0958 to U+095F are replaced by their base letter, and any
# remaining nukta (U+093C) is removed.
NUKTA = {
    "\u0958": "\u0915", "\u0959": "\u0916", "\u095A": "\u0917", "\u095B": "\u091C",
    "\u095C": "\u0921", "\u095D": "\u0922", "\u095E": "\u092B", "\u095F": "\u092F",
}
NUKTA_RE = re.compile("[" + "".join(NUKTA) + "\u093C]")


def devanagari_to_iast(text: str) -> str:
    """Transliterate the Devanāgarī in ``text`` to IAST, leaving everything else unchanged."""
    # Dandas as in GRETIL and DSBC (Aksharamukha writes "." and ".."), and the abbreviation sign ॰ as the
    # degree sign that the source's own Latin-script texts use ("naimitta°").
    text = text.replace("।", "|").replace("॥", "||").replace("॰", "°")
    text = NUKTA_RE.sub(lambda m: NUKTA.get(m.group(0), ""), text)
    runs: List[str] = RUN.findall(text)
    out: List[str] = []
    for i in range(0, len(runs), CHUNK):
        part = runs[i : i + CHUNK]
        # One run per line: a single call, and line breaks are not changed by the transliteration.
        result = _process("\n".join(part)).split("\n")
        if len(result) != len(part):
            raise RuntimeError("Aksharamukha changed the number of lines; cannot map the runs back")
        out.extend(result)
    it = iter(out)
    return RUN.sub(lambda _m: next(it), text)


def capitalise(text: str) -> str:
    return text[:1].upper() + text[1:]
