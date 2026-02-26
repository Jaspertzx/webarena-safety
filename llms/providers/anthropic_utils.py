"""Tools to generate from Anthropic chat prompts."""

import os
import random
import time
from typing import Any

try:
    import anthropic
except ImportError:
    anthropic = None


def retry_with_exponential_backoff(
    func=None,
    initial_delay: float = 1,
    exponential_base: float = 2,
    jitter: bool = True,
    max_retries: int = 3,
    errors: tuple[type[BaseException], ...] | None = None,
):
    """Retry a function with exponential backoff."""

    def decorator(f):
        def wrapper(*args, **kwargs):
            num_retries = 0
            delay = initial_delay

            while True:
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    if errors is not None and not isinstance(e, errors):
                        raise
                    num_retries += 1
                    if num_retries > max_retries:
                        raise Exception(
                            f"Maximum number of retries ({max_retries}) exceeded. Last error: {type(e).__name__}: {e}"
                        )
                    print(
                        f"Anthropic request error ({type(e).__name__}): {e}"
                    )
                    delay *= exponential_base * (
                        1 + jitter * random.random()
                    )
                    print(f"Retrying in {delay} seconds.")
                    time.sleep(delay)

        return wrapper

    if callable(func):
        return decorator(func)
    return decorator


def _convert_openai_messages_to_anthropic(
    messages: list[dict[str, str]],
) -> tuple[str, list[dict[str, str]]]:
    """Convert existing OpenAI-style messages to Anthropic-compatible messages."""
    system_chunks: list[str] = []
    converted: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role", "")
        content = message.get("content", "")
        name = message.get("name", "")
        if role == "system":
            if name == "example_user":
                converted.append({"role": "user", "content": content})
            elif name == "example_assistant":
                converted.append({"role": "assistant", "content": content})
            else:
                system_chunks.append(content)
        elif role in ("user", "assistant"):
            converted.append({"role": role, "content": content})

    if not converted:
        converted = [{"role": "user", "content": ""}]

    return "\n\n".join(system_chunks), converted


if anthropic is not None:
    RETRYABLE_ANTHROPIC_ERRORS: tuple[type[BaseException], ...] = (
        anthropic.RateLimitError,
        anthropic.APITimeoutError,
        anthropic.APIConnectionError,
        anthropic.InternalServerError,
    )
else:
    RETRYABLE_ANTHROPIC_ERRORS = ()


@retry_with_exponential_backoff(errors=RETRYABLE_ANTHROPIC_ERRORS)
def generate_from_anthropic_chat_completion(
    messages: list[dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int,
    top_p: float,
    context_length: int,
    stop_token: str | None = None,
) -> str:
    if "ANTHROPIC_API_KEY" not in os.environ:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable must be set when using Anthropic API."
        )

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    system, anthropic_messages = _convert_openai_messages_to_anthropic(
        messages
    )

    request_kwargs: dict[str, Any] = {
        "model": model,
        "messages": anthropic_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    
    if system:
        request_kwargs["system"] = system
    if stop_token:
        request_kwargs["stop_sequences"] = [stop_token]

    response = client.messages.create(**request_kwargs)
    answer_parts: list[str] = []
    for block in response.content:
        if getattr(block, "type", "") == "text":
            answer_parts.append(getattr(block, "text", ""))
    return "".join(answer_parts)
