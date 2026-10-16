import asyncio
import json
import logging
import math
import os
import threading
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Optional

import dirtyjson
from fastapi import HTTPException
from llmai.shared import (
    LLMTool,
    Message,
    ReasoningConfig,
    ResponseFormat,
    ResponseStreamCompletionChunk,
    UserMessage,
    get_response_schema,
    normalize_content_parts,
)

from enums.llm_provider import LLMProvider
from utils.llm_config import get_extra_body, has_explicit_reasoning_settings
from utils.llm_provider import get_llm_provider
from utils.schema_utils import get_schema_validation_errors
from utils.i18n import t

LOGGER = logging.getLogger(__name__)
CLIENT_DISCONNECT_POLL_SECONDS = 0.1
DisconnectChecker = Callable[[], Awaitable[bool]]
TextChunkCallback = Callable[[str], Awaitable[None]]


@dataclass(frozen=True)
class TextGenerationMetrics:
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    tokens_per_second: float
    duration_seconds: float
    estimated: bool
    thinking_tokens: Optional[int] = None
    thinking_tokens_estimated: bool = False
    supports_thinking: bool = False
    finish_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "tokens_per_second": round(self.tokens_per_second, 2),
            "duration_seconds": round(self.duration_seconds, 3),
            "estimated": self.estimated,
            "thinking_tokens": self.thinking_tokens,
            "thinking_tokens_estimated": self.thinking_tokens_estimated,
            "supports_thinking": self.supports_thinking,
        }


async def _raise_if_client_disconnected(
    disconnect_checker: Optional[DisconnectChecker],
) -> None:
    if disconnect_checker and await disconnect_checker():
        raise asyncio.CancelledError


async def _generate_structured_content(
    client: Any,
    *,
    disconnect_checker: Optional[DisconnectChecker],
    text_chunk_callback: Optional[TextChunkCallback] = None,
    **kwargs: Any,
) -> Optional[dict]:
    # Always stream, even with nothing to stream *to*. Structured generation
    # runs without an explicit max_tokens, so providers default to the model
    # ceiling, and the Anthropic SDK refuses a non-streaming request whose
    # estimated duration exceeds ten minutes -- it raises before sending
    # anything, so the call fails in seconds rather than running long. That
    # only bit callers with no disconnect checker and no chunk callback, i.e.
    # background generation, which made it look provider- or size-specific.
    # Streaming is what the SDK asks for here and is accepted identically by
    # the other providers, so it is the single path.
    completion_content: Any = None
    streamed_text: list[str] = []
    try:
        async for event in stream_generate_events(
            client,
            disconnect_checker=disconnect_checker,
            **{**kwargs, "stream": True},
        ):
            if isinstance(event, ResponseStreamCompletionChunk):
                completion_content = event.content
            elif getattr(event, "type", None) == "content":
                chunk = getattr(event, "chunk", None)
                if isinstance(chunk, str):
                    streamed_text.append(chunk)
                    if text_chunk_callback is not None:
                        await text_chunk_callback(chunk)
    except Exception as error:
        model_text = final_json_parse_error_text(error)
        content = extract_structured_content(model_text) if model_text else None
        if content is None:
            if model_text is not None:
                LOGGER.warning(
                    "Model answer is not JSON (start: %r)", model_text[:300]
                )
            raise
        LOGGER.info("Model wrapped its JSON answer; parsed it leniently")
        return content

    content = extract_structured_content(completion_content)
    if content is not None:
        if text_chunk_callback is not None and not streamed_text:
            serialized = serialize_structured_content(completion_content)
            if serialized:
                await text_chunk_callback(serialized)
        return content
    return extract_structured_content("".join(streamed_text))


def describe_schema_in_prompt() -> bool:
    """Whether to repeat the answer's JSON Schema in the prompt.

    OpenAI-compatible proxies may drop response_format (arckep with some
    models answers in plain Markdown then). On by default for the custom
    provider; STRUCTURED_OUTPUT_PROMPT=true/false forces it for any provider.
    """
    value = (os.getenv("STRUCTURED_OUTPUT_PROMPT") or "").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    try:
        return get_llm_provider() == LLMProvider.CUSTOM
    except Exception:
        return False


def reasoning_off_with_tools() -> bool:
    """Send reasoning_effort "none" when a request has tools (chat, web search).

    Reasoning models behind OpenAI-compatible proxies reject function tools
    together with reasoning_effort in /v1/chat/completions (arckep with
    gpt-6-luna: "use /v1/responses or set reasoning_effort to 'none'").
    Only for the custom provider and unless LLM_REASONING_* is set.
    """
    if has_explicit_reasoning_settings():
        return False
    try:
        return get_llm_provider() == LLMProvider.CUSTOM
    except Exception:
        return False


def json_answer_instruction(response_format: ResponseFormat) -> Optional[UserMessage]:
    schema = get_response_schema(response_format)
    if not schema:
        return None
    return UserMessage(
        content=(
            "Answer with one JSON object that matches this JSON Schema. Output only "
            "the JSON: no Markdown, no code fences, no text before or after it.\n\n"
            "JSON Schema:\n" + json.dumps(schema, ensure_ascii=False)
        )
    )


def get_generate_kwargs(
    model: str,
    messages: Sequence[Message],
    max_tokens: Optional[int] = None,
    tools: Optional[list[LLMTool]] = None,
    response_format: Optional[ResponseFormat] = None,
    reasoning: Optional[ReasoningConfig] = None,
    stream: bool = False,
) -> dict[str, Any]:
    messages = list(messages)
    if response_format is not None and describe_schema_in_prompt():
        instruction = json_answer_instruction(response_format)
        if instruction is not None:
            messages.append(instruction)
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if tools:
        kwargs["tools"] = tools
    if response_format is not None:
        kwargs["response_format"] = response_format
    if reasoning is None and tools and reasoning_off_with_tools():
        reasoning = ReasoningConfig(enabled=False)
    if reasoning is not None:
        kwargs["reasoning"] = reasoning

    extra_body = get_extra_body(uses_tool_choice=bool(tools or response_format))
    if extra_body:
        kwargs["extra_body"] = extra_body

    return kwargs


def estimate_text_tokens(value: str) -> int:
    """Return a stable approximation when a provider omits token usage."""
    return max(1, round(len(value) / 4)) if value else 0


def estimate_thinking_tokens(value: str) -> int:
    """Match llmai's visible-reasoning estimate for streamed thinking chunks."""
    return math.ceil(len(value.encode("utf-8")) / 4) if value else 0


def estimate_message_tokens(messages: Sequence[Message]) -> int:
    return sum(
        estimate_text_tokens(extract_text(getattr(message, "content", None)) or "")
        for message in messages
    )


def _usage_token_value(usage: Any, *names: str) -> Optional[int]:
    for name in names:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        if isinstance(value, (int, float)):
            return int(value)
    return None


def _usage_thinking_tokens(usage: Any) -> tuple[Optional[int], bool]:
    """Return llmai's best thinking count and whether that count is estimated."""
    if usage is None:
        return None, False

    reasoning = (
        usage.get("reasoning")
        if isinstance(usage, dict)
        else getattr(usage, "reasoning", None)
    )
    billed_tokens = _usage_token_value(reasoning, "billed_tokens")
    if billed_tokens is not None:
        billed_estimated = (
            reasoning.get("billed_estimated", False)
            if isinstance(reasoning, dict)
            else getattr(reasoning, "billed_estimated", False)
        )
        return billed_tokens, bool(billed_estimated)

    visible_tokens = _usage_token_value(reasoning, "visible_tokens")
    if visible_tokens is not None:
        return visible_tokens, True

    return _usage_token_value(usage, "thinking_tokens", "reasoning_tokens"), False


def build_text_generation_metrics(
    *,
    model: str,
    messages: Sequence[Message],
    content: str,
    streamed_thinking: str,
    completion: Any,
    started_at: float,
    model_supports_thinking: bool = False,
) -> TextGenerationMetrics:
    usage = getattr(completion, "usage", None) if completion is not None else None
    exact_input_tokens = _usage_token_value(usage, "input_tokens", "prompt_tokens")
    exact_output_tokens = _usage_token_value(
        usage, "output_tokens", "completion_tokens"
    )
    input_tokens = (
        exact_input_tokens
        if exact_input_tokens is not None
        else estimate_message_tokens(messages)
    )
    output_tokens = (
        exact_output_tokens
        if exact_output_tokens is not None
        else estimate_text_tokens(content)
    )
    thinking_tokens, thinking_tokens_estimated = _usage_thinking_tokens(usage)
    if thinking_tokens is None and streamed_thinking:
        thinking_tokens = estimate_thinking_tokens(streamed_thinking)
        thinking_tokens_estimated = True

    supports_thinking = bool(
        model_supports_thinking
        or thinking_tokens is not None
        or streamed_thinking
    )
    if (
        supports_thinking
        and exact_output_tokens is not None
        and (thinking_tokens is None or thinking_tokens_estimated)
    ):
        inferred_thinking_tokens = max(
            0,
            exact_output_tokens - estimate_text_tokens(content),
        )
        if thinking_tokens is None or inferred_thinking_tokens > thinking_tokens:
            thinking_tokens = inferred_thinking_tokens
            thinking_tokens_estimated = True
    if supports_thinking and thinking_tokens is None:
        thinking_tokens = 0
        thinking_tokens_estimated = True

    # Provider-reported output usage normally already includes reasoning
    # tokens. When usage is unavailable, however, ``output_tokens`` is only an
    # estimate of visible content. Include the separately streamed thinking
    # estimate so live throughput does not incorrectly read 0 t/s while a
    # reasoning model is actively working.
    generated_tokens = output_tokens
    if exact_output_tokens is None and thinking_tokens is not None:
        generated_tokens += thinking_tokens

    duration_seconds = (
        getattr(completion, "duration_seconds", None)
        if completion is not None
        else None
    )
    if not isinstance(duration_seconds, (int, float)) or duration_seconds <= 0:
        duration_seconds = max(time.perf_counter() - started_at, 1e-9)
    total_tokens = _usage_token_value(usage, "total_tokens")
    if total_tokens is None:
        total_tokens = input_tokens + generated_tokens

    return TextGenerationMetrics(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        tokens_per_second=generated_tokens / duration_seconds,
        duration_seconds=duration_seconds,
        estimated=exact_input_tokens is None or exact_output_tokens is None,
        thinking_tokens=thinking_tokens,
        thinking_tokens_estimated=thinking_tokens_estimated,
        supports_thinking=supports_thinking,
    )


def structured_validation_feedback_user_message(
    content: dict,
    validation_errors: list[str],
) -> UserMessage:
    max_error_count = 10
    max_json_chars = 6000

    formatted_errors = validation_errors[:max_error_count]
    if len(validation_errors) > max_error_count:
        formatted_errors.append(
            f"...and {len(validation_errors) - max_error_count} more validation errors."
        )

    previous_response = json.dumps(
        content,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    if len(previous_response) > max_json_chars:
        previous_response = previous_response[:max_json_chars] + "\n... (truncated)"

    return UserMessage(
        content=(
            "The previous JSON response did not match the required response schema.\n\n"
            "Validation errors:\n"
            + "\n".join(f"- {error}" for error in formatted_errors)
            + "\n\nPrevious invalid JSON:\n"
            + f"```json\n{previous_response}\n```\n\n"
            + "Return corrected JSON only. Make sure it fully matches the required schema."
        )
    )


async def generate_structured_with_schema_retries(
    client: Any,
    model: str,
    *,
    messages: Sequence[Message],
    response_format: ResponseFormat,
    json_schema: dict,
    strict: bool = False,
    validate_schema: bool = False,
    validate_schema_max_loop_count: int = 4,
    disconnect_checker: Optional[DisconnectChecker] = None,
    text_chunk_callback: Optional[TextChunkCallback] = None,
) -> dict:
    """
    Parse retries (inner loop) plus optional JSON Schema validation feedback loops (outer loop),
    matching the overflow-mitigation behavior from structured generation with validate_schema.
    """
    max_validation_loops = max(1, validate_schema_max_loop_count)
    working_messages: list[Message] = list(messages)

    for validation_attempt in range(max_validation_loops):
        content: Optional[dict] = None
        for attempt in range(3):
            await _raise_if_client_disconnected(disconnect_checker)
            content = await _generate_structured_content(
                client,
                disconnect_checker=disconnect_checker,
                text_chunk_callback=(
                    text_chunk_callback
                    if validation_attempt == 0 and attempt == 0
                    else None
                ),
                **get_generate_kwargs(
                    model=model,
                    messages=working_messages,
                    response_format=response_format,
                ),
            )
            if content is not None:
                break
            if attempt < 2:
                await asyncio.sleep(0.5 * (attempt + 1))

        if content is None:
            raise HTTPException(
                status_code=400,
                detail=t("err.llmUtils.llmDidNotReturnAnyContent"),
            )

        if not validate_schema:
            return content

        validation_errors = get_schema_validation_errors(
            json_schema,
            content,
            strict=strict,
        )

        if not validation_errors:
            return content

        formatted_validation_errors = " | ".join(validation_errors)
        if validation_attempt == max_validation_loops - 1:
            LOGGER.warning(
                "Validation error after max fixes, returning last response: %s",
                formatted_validation_errors,
            )
            return content

        LOGGER.warning(
            "Validation error, attempting fix %s/%s: %s",
            validation_attempt + 1,
            max_validation_loops - 1,
            formatted_validation_errors,
        )
        working_messages.append(
            structured_validation_feedback_user_message(content, validation_errors)
        )

    raise HTTPException(status_code=400, detail=t("err.llmUtils.llmDidNotReturnAnyContent"))


def extract_text(content: Any) -> Optional[str]:
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence) and not isinstance(content, (bytes, bytearray)):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
                continue
            text = getattr(part, "text", None)
            if isinstance(text, str):
                parts.append(text)
        joined = "".join(parts)
        return joined or None
    text = getattr(content, "text", None)
    if isinstance(text, str):
        return text
    return None


def final_json_parse_error_text(error: BaseException) -> Optional[str]:
    """The model text when llmai failed to json.loads a streamed structured answer.

    llmai parses the whole answer strictly at the end of the stream and raises
    if the model wrapped it (```json fences, a sentence before or after), even
    though the text itself is fine for a lenient parser.
    """
    seen: set[int] = set()
    current: Optional[BaseException] = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, json.JSONDecodeError):
            return current.doc if isinstance(current.doc, str) else None
        current = current.__cause__ or current.__context__
    return None


def unwrap_json_text(text: str) -> str:
    """The JSON object inside a model answer: drops ```json fences and text around it."""
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        stripped = stripped[first_newline + 1 :] if first_newline != -1 else ""
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
        stripped = stripped.strip()
    if not stripped.startswith(("{", "[")):
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end > start:
            stripped = stripped[start : end + 1]
    return stripped


def loads_model_json(text: str) -> Any:
    """dirtyjson.loads, then again on the unwrapped text if the model wrapped its JSON."""
    try:
        return dirtyjson.loads(text)
    except Exception:
        unwrapped = unwrap_json_text(text)
        if unwrapped == text.strip():
            raise
        return dirtyjson.loads(unwrapped)


def extract_structured_content(content: Any) -> Optional[dict]:
    if content is None:
        return None
    if isinstance(content, dict):
        return content
    if hasattr(content, "model_dump"):
        dumped = content.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped

    raw_text = content if isinstance(content, str) else extract_text(content)
    if not raw_text:
        return None

    try:
        parsed = loads_model_json(raw_text)
    except Exception:
        return None

    if isinstance(parsed, dict):
        return dict(parsed)
    return None


def serialize_structured_content(content: Any) -> Optional[str]:
    parsed = extract_structured_content(content)
    if parsed is not None:
        return json.dumps(parsed, ensure_ascii=False)

    raw_text = extract_text(content)
    if raw_text:
        return raw_text
    return None


def message_content_to_text(content: Sequence[Any] | str | None) -> Optional[str]:
    joined = "".join(
        part.text
        for part in normalize_content_parts(content)
        if isinstance(getattr(part, "text", None), str)
    )
    return joined or None


async def stream_generate_events(
    client: Any,
    *,
    disconnect_checker: Optional[DisconnectChecker] = None,
    **kwargs,
) -> AsyncGenerator[Any, None]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Any] = asyncio.Queue()
    sentinel = object()
    stop_requested = threading.Event()

    def enqueue(item: Any) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, item)
        except RuntimeError:
            pass

    def worker():
        events = None
        try:
            events = iter(client.generate(**kwargs))
            while not stop_requested.is_set():
                try:
                    event = next(events)
                except StopIteration:
                    break
                if stop_requested.is_set():
                    break
                enqueue(event)
        except Exception as exc:
            if not stop_requested.is_set():
                enqueue(exc)
        finally:
            if stop_requested.is_set() and events is not None:
                close = getattr(events, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        LOGGER.debug(
                            "Failed to close cancelled LLM stream",
                            exc_info=True,
                        )
            enqueue(sentinel)

    worker_task = asyncio.create_task(asyncio.to_thread(worker))
    completed = False
    try:
        while True:
            await _raise_if_client_disconnected(disconnect_checker)
            try:
                item = await asyncio.wait_for(
                    queue.get(),
                    timeout=(
                        CLIENT_DISCONNECT_POLL_SECONDS
                        if disconnect_checker
                        else None
                    ),
                )
            except asyncio.TimeoutError:
                continue
            if item is sentinel:
                completed = True
                break
            if isinstance(item, Exception):
                raise item
            yield item
    except asyncio.CancelledError:
        LOGGER.info("LLM stream cancelled because the client disconnected")
        raise
    finally:
        stop_requested.set()
        if completed or worker_task.done():
            await worker_task
        else:
            worker_task.add_done_callback(
                lambda task: None if task.cancelled() else task.exception()
            )
