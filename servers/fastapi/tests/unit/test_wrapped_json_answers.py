"""Models behind OpenAI-compatible proxies (arckep) may wrap a JSON answer in
```json fences or a sentence. llmai then fails its strict final json.loads even
though the text is usable; Presenton parses it leniently instead of failing."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from llmai.shared.errors import LLMError

from utils import llm_utils
from utils.llm_calls import generate_presentation_outlines as outlines_module
from utils.llm_utils import (
    final_json_parse_error_text,
    loads_model_json,
    unwrap_json_text,
)

OUTLINE = {"slides": [{"content": "Первый слайд"}, {"content": "Второй слайд"}]}
FENCED = "```json\n" + json.dumps(OUTLINE, ensure_ascii=False) + "\n```"


def llmai_final_parse_error(text: str) -> LLMError:
    """What llmai raises: LLMError from the JSONDecodeError of its json.loads."""
    try:
        json.loads(text)
    except json.JSONDecodeError as decode_error:
        try:
            raise LLMError(500, str(decode_error)) from decode_error
        except LLMError as error:
            return error
    raise AssertionError("text is valid JSON")


def test_unwrap_fences_and_text_around():
    assert json.loads(unwrap_json_text(FENCED)) == OUTLINE
    assert json.loads(unwrap_json_text("Вот план:\n" + json.dumps(OUTLINE) + "\nГотово.")) == OUTLINE
    assert unwrap_json_text('  {"a": 1} ') == '{"a": 1}'
    assert loads_model_json(FENCED) == OUTLINE
    with pytest.raises(Exception):
        loads_model_json("not json at all")


def test_the_model_text_is_found_in_the_error_chain():
    error = llmai_final_parse_error(FENCED)
    assert final_json_parse_error_text(error) == FENCED
    assert final_json_parse_error_text(LLMError(500, "rate limited")) is None
    assert llm_utils.extract_structured_content(FENCED) == OUTLINE


def test_structured_generation_parses_a_wrapped_answer(monkeypatch):
    async def fake_stream(_client, **_kwargs):
        for piece in (FENCED[:10], FENCED[10:]):
            yield SimpleNamespace(type="content", chunk=piece)
        raise llmai_final_parse_error(FENCED)

    monkeypatch.setattr(llm_utils, "stream_generate_events", fake_stream)
    content = asyncio.run(llm_utils._generate_structured_content(object(), disconnect_checker=None))
    assert content == OUTLINE


def test_structured_generation_still_fails_on_garbage_and_other_errors(monkeypatch):
    async def garbage(_client, **_kwargs):
        yield SimpleNamespace(type="content", chunk="sorry, I cannot")
        raise llmai_final_parse_error("sorry, I cannot")

    monkeypatch.setattr(llm_utils, "stream_generate_events", garbage)
    with pytest.raises(LLMError):
        asyncio.run(llm_utils._generate_structured_content(object(), disconnect_checker=None))

    async def unavailable(_client, **_kwargs):
        raise LLMError(503, "upstream down")
        yield  # pragma: no cover

    monkeypatch.setattr(llm_utils, "stream_generate_events", unavailable)
    with pytest.raises(LLMError, match="upstream down"):
        asyncio.run(llm_utils._generate_structured_content(object(), disconnect_checker=None))


def _collect_outline(monkeypatch, fake_stream):
    monkeypatch.setattr(outlines_module, "stream_generate_events", fake_stream)
    monkeypatch.setattr(outlines_module, "get_client", lambda **_kwargs: object())
    monkeypatch.setattr(outlines_module, "get_llm_config", lambda **_kwargs: None)
    monkeypatch.setattr(outlines_module, "get_model", lambda: "test-model")
    monkeypatch.setattr(outlines_module, "get_generate_kwargs", lambda **kwargs: {})

    async def collect():
        chunks = []
        async for item in outlines_module.generate_ppt_outline(
            "тема", 2, "Russian", web_search=False, emit_statuses=False
        ):
            chunks.append(item)
        return chunks

    return asyncio.run(collect())


def test_outline_stream_is_not_an_error_when_only_the_strict_parse_failed(monkeypatch):
    async def wrapped(_client, **_kwargs):
        yield SimpleNamespace(type="content", chunk=FENCED)
        raise llmai_final_parse_error(FENCED)

    chunks = _collect_outline(monkeypatch, wrapped)
    assert "".join(c for c in chunks if isinstance(c, str)) == FENCED
    assert loads_model_json("".join(chunks)) == OUTLINE

    # Nothing streamed: the text from the error is handed over instead.
    async def silent(_client, **_kwargs):
        raise llmai_final_parse_error(FENCED)
        yield  # pragma: no cover

    assert _collect_outline(monkeypatch, silent) == [FENCED]


def test_outline_stream_reports_real_provider_errors(monkeypatch):
    from fastapi import HTTPException

    async def unavailable(_client, **_kwargs):
        raise LLMError(503, "upstream down")
        yield  # pragma: no cover

    chunks = _collect_outline(monkeypatch, unavailable)
    assert len(chunks) == 1 and isinstance(chunks[0], HTTPException)


def test_custom_provider_gets_the_schema_in_the_prompt(monkeypatch):
    from llmai.shared import JSONSchemaResponse, UserMessage

    schema = {"type": "object", "properties": {"slides": {"type": "array"}}, "required": ["slides"]}
    response_format = JSONSchemaResponse(name="response", json_schema=schema, strict=False)
    messages = [UserMessage(content="Сделай план")]
    monkeypatch.setattr(llm_utils, "get_extra_body", lambda **_kwargs: None)

    monkeypatch.delenv("STRUCTURED_OUTPUT_PROMPT", raising=False)
    monkeypatch.setenv("LLM", "custom")
    kwargs = llm_utils.get_generate_kwargs(model="m", messages=messages, response_format=response_format)
    assert len(kwargs["messages"]) == 2 and len(messages) == 1
    instruction = kwargs["messages"][-1].content
    assert "JSON Schema" in instruction and '"slides"' in instruction and "no code fences" in instruction

    # Not for providers that honour response_format, unless asked.
    monkeypatch.setenv("LLM", "openai")
    assert len(llm_utils.get_generate_kwargs(model="m", messages=messages, response_format=response_format)["messages"]) == 1
    monkeypatch.setenv("STRUCTURED_OUTPUT_PROMPT", "true")
    assert len(llm_utils.get_generate_kwargs(model="m", messages=messages, response_format=response_format)["messages"]) == 2
    monkeypatch.setenv("LLM", "custom")
    monkeypatch.setenv("STRUCTURED_OUTPUT_PROMPT", "false")
    assert len(llm_utils.get_generate_kwargs(model="m", messages=messages, response_format=response_format)["messages"]) == 1
    # Plain text requests are untouched.
    monkeypatch.delenv("STRUCTURED_OUTPUT_PROMPT")
    assert len(llm_utils.get_generate_kwargs(model="m", messages=messages)["messages"]) == 1


def test_custom_provider_turns_reasoning_off_when_tools_are_sent(monkeypatch):
    from llmai.shared import UserMessage, WebSearchTool

    messages = [UserMessage(content="Добавь таблицу")]
    monkeypatch.setattr(llm_utils, "get_extra_body", lambda **_kwargs: None)
    for name in ("LLM_REASONING_MODE", "LLM_REASONING_EFFORT", "LLM_REASONING_BUDGET_TOKENS"):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv("LLM", "custom")
    kwargs = llm_utils.get_generate_kwargs(model="m", messages=messages, tools=[WebSearchTool()])
    assert kwargs["reasoning"].enabled is False  # sent as reasoning_effort "none"
    # No tools: the profile decides as before.
    assert "reasoning" not in llm_utils.get_generate_kwargs(model="m", messages=messages)
    # An explicit setting wins.
    monkeypatch.setenv("LLM_REASONING_EFFORT", "high")
    assert "reasoning" not in llm_utils.get_generate_kwargs(model="m", messages=messages, tools=[WebSearchTool()])
    # Other providers are untouched.
    monkeypatch.delenv("LLM_REASONING_EFFORT")
    monkeypatch.setenv("LLM", "openai")
    assert "reasoning" not in llm_utils.get_generate_kwargs(model="m", messages=messages, tools=[WebSearchTool()])
