import os
from unittest.mock import patch, MagicMock

from local.normalizer import normalize_command


def make_mock_response(command, confidence, category, reason):
    mock = MagicMock()
    mock.content[0].text = (
        f'{{"command": "{command}", "confidence": {confidence}, '
        f'"category": "{category}", "reason": "{reason}"}}'
    )
    return mock


class TestNormalizeCommand:
    def test_empty_input(self):
        r = normalize_command("")
        assert r.normalized == "unknown"
        assert r.confidence == 0.0
        assert r.reason == "empty_input"

    def test_none_input(self):
        r = normalize_command(None)
        assert r.normalized == "unknown"

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_turn_on(self):
        with patch("local.normalizer.anthropic.Anthropic") as mock_client:
            mock_client.return_value.messages.create.return_value = make_mock_response(
                "on", 0.99, "clear", "user wants light on")
            r = normalize_command("turn the light on")
            assert r.normalized == "on"
            assert r.category == "clear"

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_turn_off(self):
        with patch("local.normalizer.anthropic.Anthropic") as mock_client:
            mock_client.return_value.messages.create.return_value = make_mock_response(
                "off", 0.99, "clear", "user wants light off")
            r = normalize_command("turn off")
            assert r.normalized == "off"

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_unknown(self):
        with patch("local.normalizer.anthropic.Anthropic") as mock_client:
            mock_client.return_value.messages.create.return_value = make_mock_response(
                "unknown", 0.95, "unrelated", "not a light command")
            r = normalize_command("hello how are you")
            assert r.normalized == "unknown"

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_conflict_category(self):
        with patch("local.normalizer.anthropic.Anthropic") as mock_client:
            mock_client.return_value.messages.create.return_value = make_mock_response(
                "unknown", 0.5, "conflict", "both on and off")
            r = normalize_command("turn it on and off")
            assert r.normalized == "unknown"
            assert r.category == "conflict"

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_llm_error_falls_back_to_keywords(self):
        with patch("local.normalizer.anthropic.Anthropic") as mock_client:
            mock_client.return_value.messages.create.side_effect = RuntimeError("boom")
            r = normalize_command("turn on the light")
            assert r.normalized == "on"          # recovered via keyword fallback
            assert "keyword" in r.reason

    @patch.dict(os.environ, {}, clear=True)
    def test_no_api_key_uses_fallback(self):
        r = normalize_command("turn off the light")
        assert r.normalized == "off"
        assert "keyword" in r.reason


class TestInstrumentation:
    def test_fast_path_records_latency_and_no_tokens(self):
        r = normalize_command("turn on the light")
        assert r.used_llm is False
        assert r.input_tokens == 0 and r.output_tokens == 0
        assert r.latency_ms >= 0.0

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_llm_path_records_token_usage(self):
        with patch("local.normalizer.anthropic.Anthropic") as mock_client:
            response = make_mock_response("unknown", 0.5, "ambiguous", "unclear")
            response.usage.input_tokens = 187
            response.usage.output_tokens = 41
            mock_client.return_value.messages.create.return_value = response

            r = normalize_command("do something with the light")
            assert r.used_llm is True
            assert (r.input_tokens, r.output_tokens) == (187, 41)
            assert r.latency_ms >= 0.0

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_unreadable_usage_does_not_break_classification(self):
        with patch("local.normalizer.anthropic.Anthropic") as mock_client:
            response = make_mock_response("unknown", 0.5, "ambiguous", "unclear")
            response.usage.input_tokens = "not-a-number"
            mock_client.return_value.messages.create.return_value = response

            r = normalize_command("do something with the light")
            assert r.category == "ambiguous"
            assert r.input_tokens == 0

    def test_fallback_path_reports_no_llm_usage(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), \
             patch("local.normalizer.anthropic.Anthropic") as mock_client:
            mock_client.return_value.messages.create.side_effect = RuntimeError("boom")
            r = normalize_command("what about the light")
            assert r.used_llm is False
            assert r.input_tokens == 0


class TestKeywordFallbackBranches:
    """The offline path has to stand on its own — it is what answers when the
    API key is missing or the call fails."""

    @patch.dict(os.environ, {}, clear=True)
    def test_negated_command_is_not_executed(self):
        r = normalize_command("don't turn on the light")
        assert r.normalized == "unknown"
        assert r.category == "negated"

    @patch.dict(os.environ, {}, clear=True)
    def test_conflicting_command_is_flagged(self):
        r = normalize_command("turn it on and off")
        assert r.category == "conflict"

    @patch.dict(os.environ, {}, clear=True)
    def test_ambiguous_input_without_api_key_stays_offline(self):
        # Reaches the API-key check (the fast path does not answer this one).
        r = normalize_command("what about the light")
        assert r.used_llm is False
        assert r.normalized == "unknown"


class TestMalformedLLMResponses:
    """A classifier that trusts whatever JSON comes back is one bad response
    away from executing something the user never asked for."""

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_json_wrapped_in_markdown_fences_is_parsed(self):
        with patch("local.normalizer.anthropic.Anthropic") as mock_client:
            mock = MagicMock()
            mock.content[0].text = (
                '```json\n{"command": "off", "confidence": 0.9, '
                '"category": "clear", "reason": "fenced"}\n```'
            )
            mock.usage.input_tokens = 100
            mock.usage.output_tokens = 20
            mock_client.return_value.messages.create.return_value = mock

            r = normalize_command("hmm the light")
            assert r.normalized == "off"
            assert r.category == "clear"

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_out_of_vocabulary_command_becomes_unknown(self):
        with patch("local.normalizer.anthropic.Anthropic") as mock_client:
            mock_client.return_value.messages.create.return_value = make_mock_response(
                "dim", 0.9, "clear", "model invented a command")
            r = normalize_command("dim the light a bit")
            assert r.normalized == "unknown"

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_out_of_vocabulary_category_becomes_error(self):
        with patch("local.normalizer.anthropic.Anthropic") as mock_client:
            mock_client.return_value.messages.create.return_value = make_mock_response(
                "unknown", 0.5, "confused", "model invented a category")
            r = normalize_command("what about the light")
            assert r.category == "error"
