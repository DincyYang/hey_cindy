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
