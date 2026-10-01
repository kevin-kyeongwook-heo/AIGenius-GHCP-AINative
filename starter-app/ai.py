"""AI-powered task enhancements."""

import json
import re
from typing import Any

from ai_client import (
    AzureOpenAIConfigurationError,
    create_azure_openai_client,
    load_azure_openai_config,
)

SYSTEM_PROMPT = """You categorize tasks for a command-line task manager.
Return exactly one short, lowercase category tag and nothing else.
Use only letters and numbers; do not include spaces, punctuation, Markdown,
explanations, or multiple alternatives. Prefer a useful broad category such as
work, personal, health, finance, shopping, learning, travel, or devops."""

MAX_TAG_LENGTH = 50
TAG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class TagSuggestionError(RuntimeError):
    """Raised when Azure OpenAI cannot provide a usable tag suggestion."""


def _extract_response_content(response: Any) -> str:
    """Extract text content from an Azure OpenAI chat completion."""
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise TagSuggestionError("Azure OpenAI returned an invalid response.") from exc

    if not isinstance(content, str) or not content.strip():
        raise TagSuggestionError("Azure OpenAI returned an empty tag suggestion.")
    return content


def _normalize_tag(content: str) -> str:
    """Normalize one model response into a schema-safe task tag."""
    candidate = content.strip()

    if candidate.startswith("{"):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise TagSuggestionError("Azure OpenAI returned malformed tag data.") from exc
        candidate = payload.get("tag", "") if isinstance(payload, dict) else ""

    if not isinstance(candidate, str):
        raise TagSuggestionError("Azure OpenAI returned malformed tag data.")

    candidate = candidate.strip().strip("`\"'").strip().lower()
    if candidate.startswith("tag:"):
        candidate = candidate[4:].strip()

    if any(separator in candidate for separator in (",", ";", "\n", "\r")):
        raise TagSuggestionError("Azure OpenAI returned multiple tag suggestions.")

    candidate = re.sub(r"[\s_]+", "-", candidate)
    candidate = candidate.strip(".!?#*-")

    if (
        not candidate
        or len(candidate) > MAX_TAG_LENGTH
        or TAG_PATTERN.fullmatch(candidate) is None
    ):
        raise TagSuggestionError("Azure OpenAI returned an invalid tag suggestion.")
    return candidate


def suggest_tag(task_name: str, description: str) -> str | None:
    """Suggest one normalized tag for a task, or None when AI is not configured."""
    try:
        config = load_azure_openai_config()
    except AzureOpenAIConfigurationError:
        return None

    client = create_azure_openai_client(config)
    try:
        response = client.chat.completions.create(
            model=config.deployment,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Task name: {task_name.strip()}\n"
                        f"Description: {description.strip() or '(none)'}"
                    ),
                },
            ],
            temperature=0,
            max_tokens=20,
        )
    except Exception as exc:
        raise TagSuggestionError("Azure OpenAI tag suggestion request failed.") from exc

    return _normalize_tag(_extract_response_content(response))
