import pytest

from utils.llm_calls import edit_slide, generate_presentation_outlines, generate_slide_content
from utils.presentation_language import parse_auto_language, resolve_outline_prompt_language


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Auto (Russian)", (True, "Russian")),
        ("auto (English)", (True, "English")),
        ("Auto", (True, None)),
        ("auto-detect", (True, None)),
        ("", (True, None)),
        (None, (True, None)),
        ("Auto ()", (True, None)),
        ("Russian (Русский)", (False, None)),
        ("English", (False, None)),
        ("Automotive jargon", (False, None)),
    ],
)
def test_parse_auto_language(value, expected):
    assert parse_auto_language(value) == expected


def test_outline_prompt_language_uses_the_fallback_only_when_unclear():
    russian = resolve_outline_prompt_language("Auto (Russian)")
    assert russian.startswith("auto-detect")
    assert russian.endswith("use Russian")
    assert resolve_outline_prompt_language("Auto") == "auto-detect"
    assert resolve_outline_prompt_language("Russian (Русский)") == "Russian (Русский)"
    # The outline and edit prompts share the same resolution.
    assert generate_presentation_outlines._resolve_prompt_language("Auto (Russian)") == russian
    assert edit_slide._resolve_prompt_language("Auto (Russian)") == russian


def test_slide_content_follows_the_outline_language_for_auto():
    auto = generate_slide_content.AUTO_DETECT_LANGUAGE_INSTRUCTION
    assert generate_slide_content._resolve_prompt_language("Auto (Russian)") == auto
    assert generate_slide_content._resolve_prompt_language("Auto (English)") == auto
    assert generate_slide_content._resolve_prompt_language(None) == auto
    assert generate_slide_content._resolve_prompt_language(" German (Deutsch) ") == "German (Deutsch)"
