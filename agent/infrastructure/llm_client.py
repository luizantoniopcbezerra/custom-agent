import time

from openai import NOT_GIVEN, OpenAI, RateLimitError
from openai.types.chat import ChatCompletion
from openai.types.chat import ChatCompletionMessageParam as MessageParam
from openai.types.chat import ChatCompletionToolParam as ToolParam
from rich.console import Console

from agent.infrastructure.rate_limiter import RateLimiter

console = Console()

_MAX_RETRIES = 3
_DEFAULT_RETRY_WAIT = 30  # seconds, used when provider doesn't send Retry-After


class LLMClient:
    """OpenAI-compatible client pointing to OpenRouter, with integrated rate limiting."""

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        rate_limiter: RateLimiter,
    ) -> None:
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        self._rate_limiter = rate_limiter

    def chat(
        self,
        messages: list[MessageParam],
        tools: list[ToolParam] | None = None,
        model: str | None = None,
    ) -> ChatCompletion:
        """Send a chat completion request, respecting rate limits.

        Retries up to _MAX_RETRIES times on upstream 429, using Retry-After when provided.
        """
        self._rate_limiter.wait_if_needed()
        resolved_model = model or self._model

        for attempt in range(_MAX_RETRIES):
            try:
                start = time.monotonic()
                response = self._client.chat.completions.create(
                    model=resolved_model,
                    messages=messages,
                    tools=tools if tools is not None else NOT_GIVEN,
                    tool_choice="auto" if tools is not None else NOT_GIVEN,
                )
                self._rate_limiter.record_request()
                elapsed = time.monotonic() - start
                console.print(
                    f"[LLM] model={resolved_model} msgs={len(messages)} time={elapsed:.1f}s"
                )
                return response

            except RateLimitError as exc:
                if attempt == _MAX_RETRIES - 1:
                    raise
                wait = _DEFAULT_RETRY_WAIT
                try:
                    wait = int(exc.body["error"]["metadata"]["retry_after_seconds"]) + 1
                except (KeyError, TypeError, ValueError):
                    pass
                console.print(
                    f"[LLM] 429 from upstream ({resolved_model}), "
                    f"retrying in {wait}s (attempt {attempt + 1}/{_MAX_RETRIES})..."
                )
                time.sleep(wait)

        raise RuntimeError("unreachable")
