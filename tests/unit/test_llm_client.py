from unittest.mock import MagicMock, patch

import pytest

from agent.infrastructure.llm_client import LLMClient
from agent.infrastructure.rate_limiter import RateLimiter


def _make_client() -> tuple[LLMClient, MagicMock, MagicMock]:
    """Return (client, mock_openai_create, mock_rate_limiter)."""
    mock_create = MagicMock()
    mock_create.return_value = MagicMock()  # fake ChatCompletion

    mock_rate_limiter = MagicMock(spec=RateLimiter)

    with patch("agent.infrastructure.llm_client.OpenAI") as mock_openai_cls:
        mock_openai_cls.return_value.chat.completions.create = mock_create
        client = LLMClient(
            model="test-model",
            base_url="https://openrouter.ai/api/v1",
            api_key="sk-test",
            rate_limiter=mock_rate_limiter,
        )
        # Attach the mock so tests can inspect calls
        client._mock_create = mock_create  # type: ignore[attr-defined]

    return client, mock_create, mock_rate_limiter


def test_chat_calls_wait_before_create() -> None:
    client, mock_create, mock_limiter = _make_client()
    messages: list = [{"role": "user", "content": "hi"}]

    call_order: list[str] = []
    mock_limiter.wait_if_needed.side_effect = lambda: call_order.append("wait")
    mock_create.side_effect = lambda **_: call_order.append("create") or MagicMock()
    mock_limiter.record_request.side_effect = lambda: call_order.append("record")

    client.chat(messages)

    assert call_order == ["wait", "create", "record"]


def test_chat_without_tools_does_not_pass_tools_to_sdk() -> None:
    client, mock_create, _ = _make_client()
    messages: list = [{"role": "user", "content": "hi"}]

    client.chat(messages, tools=None)

    _, kwargs = mock_create.call_args
    # tools and tool_choice should be NOT_GIVEN (falsy / sentinel), not a list
    from openai import NOT_GIVEN

    assert kwargs.get("tools") is NOT_GIVEN
    assert kwargs.get("tool_choice") is NOT_GIVEN


def test_chat_with_tools_passes_tools_to_sdk() -> None:
    client, mock_create, _ = _make_client()
    messages: list = [{"role": "user", "content": "hi"}]
    tools: list = [{"type": "function", "function": {"name": "read_file", "parameters": {}}}]

    client.chat(messages, tools=tools)  # type: ignore[arg-type]

    _, kwargs = mock_create.call_args
    assert kwargs.get("tools") == tools
    assert kwargs.get("tool_choice") == "auto"


def test_chat_returns_completion_object() -> None:
    client, mock_create, _ = _make_client()
    fake_completion = MagicMock()
    mock_create.return_value = fake_completion

    result = client.chat([{"role": "user", "content": "hi"}])  # type: ignore[list-item]

    assert result is fake_completion


def test_api_key_not_logged(capsys: pytest.CaptureFixture[str]) -> None:
    client, _, _ = _make_client()
    client.chat([{"role": "user", "content": "hi"}])  # type: ignore[list-item]

    captured = capsys.readouterr()
    assert "sk-test" not in captured.out
    assert "sk-test" not in captured.err
