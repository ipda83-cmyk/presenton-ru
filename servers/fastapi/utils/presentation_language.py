"""Presentation (content) language values sent by the frontend.

Besides concrete languages ("Russian (Русский)", "English", ...) the picker has
an "Auto (<fallback>)" option: detect the language from the user's content and
use the fallback only when the content does not make it clear. The frontend
sends "Auto (Russian)"; older clients and the API may send "Auto (English)",
"auto" or nothing.
"""

import re
from typing import Optional

_AUTO_LANGUAGE = re.compile(
    r"^auto(?:[-\s]?detect)?\s*(?:\((?P<fallback>[^()]*)\))?$", re.IGNORECASE
)


def parse_auto_language(language: Optional[str]) -> tuple[bool, Optional[str]]:
    """(is_auto, fallback language). Empty values count as auto without fallback."""
    value = str(language or "").strip()
    if not value:
        return True, None
    match = _AUTO_LANGUAGE.match(value)
    if not match:
        return False, None
    fallback = (match.group("fallback") or "").strip()
    return True, fallback or None


def resolve_outline_prompt_language(language: Optional[str]) -> str:
    """Language line for outline/edit prompts; always starts with "auto-detect"
    for the auto option so the system prompt's auto-detect rule applies."""
    is_auto, fallback = parse_auto_language(language)
    if not is_auto:
        return str(language).strip()
    if fallback:
        return (
            "auto-detect from the content; if the content does not make the "
            f"language clear, use {fallback}"
        )
    return "auto-detect"
