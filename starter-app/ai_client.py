"""Azure OpenAI client configuration for the task manager."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import AzureOpenAI

AZURE_OPENAI_API_VERSION = "2024-02-01"
AZURE_OPENAI_TIMEOUT_SECONDS = 5.0


class AzureOpenAIConfigurationError(ValueError):
    """Raised when required Azure OpenAI configuration is missing."""


@dataclass(frozen=True)
class AzureOpenAIConfig:
    """Validated settings required to use Azure OpenAI."""

    endpoint: str
    api_key: str
    deployment: str


def load_azure_openai_config() -> AzureOpenAIConfig:
    """Load and validate Azure OpenAI settings from the environment.

    A local ``.env`` file is loaded when present. Environment variables already
    set by the caller take precedence over values in that file.

    Raises:
        AzureOpenAIConfigurationError: If any required setting is missing.

    Returns:
        The validated Azure OpenAI configuration.
    """
    load_dotenv()

    variable_names = (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_DEPLOYMENT",
    )
    values = {name: os.getenv(name, "").strip() for name in variable_names}
    missing_variables = [name for name, value in values.items() if not value]

    if missing_variables:
        missing_list = ", ".join(missing_variables)
        raise AzureOpenAIConfigurationError(
            "Azure OpenAI configuration is incomplete. "
            f"Set {missing_list} in the environment or a .env file."
        )

    return AzureOpenAIConfig(
        endpoint=values["AZURE_OPENAI_ENDPOINT"],
        api_key=values["AZURE_OPENAI_API_KEY"],
        deployment=values["AZURE_OPENAI_DEPLOYMENT"],
    )


def create_azure_openai_client(
    config: AzureOpenAIConfig | None = None,
) -> AzureOpenAI:
    """Create a typed Azure OpenAI client from validated configuration.

    Args:
        config: Optional preloaded configuration. When omitted, configuration
            is loaded from the environment.

    Returns:
        A configured Azure OpenAI client.

    Raises:
        AzureOpenAIConfigurationError: If required configuration is missing.
    """
    resolved_config = config or load_azure_openai_config()
    return AzureOpenAI(
        api_key=resolved_config.api_key,
        azure_endpoint=resolved_config.endpoint,
        api_version=AZURE_OPENAI_API_VERSION,
        timeout=AZURE_OPENAI_TIMEOUT_SECONDS,
    )
