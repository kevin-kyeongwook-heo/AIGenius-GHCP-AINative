"""Tests for Azure OpenAI configuration and task tag suggestions."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

import ai
import ai_client
import app
from ai import TagSuggestionError, suggest_tag
from ai_client import (
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_TIMEOUT_SECONDS,
    AzureOpenAIConfigurationError,
    create_azure_openai_client,
    load_azure_openai_config,
)

AZURE_ENVIRONMENT = {
    "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
    "AZURE_OPENAI_API_KEY": "test-api-key",
    "AZURE_OPENAI_DEPLOYMENT": "test-deployment",
}


def _chat_response(content: object) -> SimpleNamespace:
    """Build a minimal chat completion response for tests."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@pytest.fixture()
def azure_environment(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Set complete fake Azure OpenAI configuration."""
    monkeypatch.setattr(ai_client, "load_dotenv", lambda: None)
    for variable_name, value in AZURE_ENVIRONMENT.items():
        monkeypatch.setenv(variable_name, value)
    return AZURE_ENVIRONMENT


@pytest.fixture()
def mocked_chat_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace Azure OpenAI client creation with a network-free mock."""
    client = MagicMock()
    monkeypatch.setattr(ai, "create_azure_openai_client", MagicMock(return_value=client))
    return client


class TestAzureOpenAIClient:
    def test_loads_complete_configuration(
        self, azure_environment: dict[str, str]
    ) -> None:
        config = load_azure_openai_config()

        assert config.endpoint == azure_environment["AZURE_OPENAI_ENDPOINT"]
        assert config.api_key == azure_environment["AZURE_OPENAI_API_KEY"]
        assert config.deployment == azure_environment["AZURE_OPENAI_DEPLOYMENT"]

    @pytest.mark.parametrize("missing_variable", AZURE_ENVIRONMENT)
    def test_rejects_each_missing_required_variable(
        self,
        missing_variable: str,
        azure_environment: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv(missing_variable)

        with pytest.raises(AzureOpenAIConfigurationError, match=missing_variable):
            load_azure_openai_config()

    def test_creates_client_with_timeout_and_no_network_call(
        self,
        azure_environment: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        client = object()
        azure_openai = MagicMock(return_value=client)
        monkeypatch.setattr(ai_client, "AzureOpenAI", azure_openai)

        assert create_azure_openai_client() is client
        azure_openai.assert_called_once_with(
            api_key=azure_environment["AZURE_OPENAI_API_KEY"],
            azure_endpoint=azure_environment["AZURE_OPENAI_ENDPOINT"],
            api_version=AZURE_OPENAI_API_VERSION,
            timeout=AZURE_OPENAI_TIMEOUT_SECONDS,
        )


class TestSuggestTag:
    def test_returns_normalized_tag_from_structured_response(
        self,
        azure_environment: dict[str, str],
        mocked_chat_client: MagicMock,
    ) -> None:
        mocked_chat_client.chat.completions.create.return_value = _chat_response(
            '{"tag": "Dev Ops"}'
        )

        assert suggest_tag("Deploy app", "Run the release pipeline") == "dev-ops"
        mocked_chat_client.chat.completions.create.assert_called_once()
        request = mocked_chat_client.chat.completions.create.call_args.kwargs
        assert request["model"] == azure_environment["AZURE_OPENAI_DEPLOYMENT"]
        assert request["temperature"] == 0
        system_prompt = request["messages"][0]["content"].lower()
        assert "exactly one" in system_prompt
        assert "lowercase" in system_prompt
        assert "punctuation" in system_prompt
        assert "Deploy app" in request["messages"][1]["content"]

    @pytest.mark.parametrize(
        ("model_output", "expected"),
        [
            ("  TAG: Dev_Ops!  ", "dev-ops"),
            ('"PERSONAL"', "personal"),
            ("`work`", "work"),
        ],
    )
    def test_normalizes_plain_text_responses(
        self,
        model_output: str,
        expected: str,
        azure_environment: dict[str, str],
        mocked_chat_client: MagicMock,
    ) -> None:
        mocked_chat_client.chat.completions.create.return_value = _chat_response(
            model_output
        )

        assert suggest_tag("Task", "") == expected

    @pytest.mark.parametrize(
        "model_output",
        [
            "",
            "   ",
            None,
            '{"category": "work"}',
            '{"tag":',
            "work, work",
            "work;personal",
            "work\npersonal",
        ],
    )
    def test_rejects_empty_malformed_or_multiple_tag_output(
        self,
        model_output: object,
        azure_environment: dict[str, str],
        mocked_chat_client: MagicMock,
    ) -> None:
        mocked_chat_client.chat.completions.create.return_value = _chat_response(
            model_output
        )

        with pytest.raises(TagSuggestionError):
            suggest_tag("Task", "")

    def test_rejects_response_without_choices(
        self,
        azure_environment: dict[str, str],
        mocked_chat_client: MagicMock,
    ) -> None:
        mocked_chat_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[]
        )

        with pytest.raises(TagSuggestionError, match="invalid response"):
            suggest_tag("Task", "")

    def test_wraps_api_failure(
        self,
        azure_environment: dict[str, str],
        mocked_chat_client: MagicMock,
    ) -> None:
        mocked_chat_client.chat.completions.create.side_effect = RuntimeError(
            "service unavailable"
        )

        with pytest.raises(TagSuggestionError, match="request failed"):
            suggest_tag("Task", "")

    @pytest.mark.parametrize("missing_variable", AZURE_ENVIRONMENT)
    def test_returns_none_without_complete_configuration(
        self,
        missing_variable: str,
        azure_environment: dict[str, str],
        mocked_chat_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv(missing_variable)

        assert suggest_tag("Task", "") is None
        mocked_chat_client.chat.completions.create.assert_not_called()


class TestAddWithTagSuggestion:
    def test_add_saves_and_displays_suggested_tag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        suggest = MagicMock(return_value="devops")
        monkeypatch.setattr(app, "suggest_tag", suggest)

        result = CliRunner().invoke(
            app.cli,
            ["add", "Deploy app", "--description", "Release to production"],
        )

        assert result.exit_code == 0
        assert app.load_tasks()[0]["tags"] == ["devops"]
        assert "AI suggested tag: devops" in result.output
        suggest.assert_called_once_with("Deploy app", "Release to production")

    def test_add_with_manual_tags_skips_ai_and_keeps_unique_inputs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        suggest = MagicMock()
        monkeypatch.setattr(app, "suggest_tag", suggest)

        result = CliRunner().invoke(
            app.cli,
            ["add", "Deploy app", "--tag", "work", "--tag", "devops"],
        )

        assert result.exit_code == 0
        assert app.load_tasks()[0]["tags"] == ["work", "devops"]
        assert "AI suggested tag" not in result.output
        suggest.assert_not_called()

    def test_no_ai_flag_skips_suggestion(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        suggest = MagicMock()
        monkeypatch.setattr(app, "suggest_tag", suggest)

        result = CliRunner().invoke(app.cli, ["add", "Deploy app", "--no-ai"])

        assert result.exit_code == 0
        assert app.load_tasks()[0]["tags"] == []
        suggest.assert_not_called()

    def test_api_failure_warns_but_still_saves_task(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            app,
            "suggest_tag",
            MagicMock(side_effect=TagSuggestionError("request failed")),
        )

        result = CliRunner().invoke(app.cli, ["add", "Deploy app"])

        assert result.exit_code == 0
        assert app.load_tasks()[0]["tags"] == []
        assert "AI tag suggestion failed" in result.output

    def test_missing_configuration_saves_without_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(app, "suggest_tag", MagicMock(return_value=None))

        result = CliRunner().invoke(app.cli, ["add", "Deploy app"])

        assert result.exit_code == 0
        assert app.load_tasks()[0]["tags"] == []
        assert "AI suggested tag" not in result.output
        assert "AI tag suggestion failed" not in result.output

    def test_help_documents_no_ai_flag(self) -> None:
        result = CliRunner().invoke(app.cli, ["add", "--help"])

        assert result.exit_code == 0
        assert "--no-ai" in result.output
