from normalizer import normalize_command
from unittest.mock import patch, MagicMock

def make_mock_response(command, confidence, reason):
    mock = MagicMock()
    mock.content[0].text = f'{{"command": "{command}", "confidence": {confidence}, "reason": "{reason}"}}'
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

    def test_turn_on(self):
        with patch("normalizer.anthropic.Anthropic") as mock_client:
            mock_client.return_value.messages.create.return_value = make_mock_response("on", 0.99, "user wants light on")
            r = normalize_command("turn the light on")
            assert r.normalized == "on"

    def test_turn_off(self):
        with patch("normalizer.anthropic.Anthropic") as mock_client:
            mock_client.return_value.messages.create.return_value = make_mock_response("off", 0.99, "user wants light off")
            r = normalize_command("turn off")
            assert r.normalized == "off"

    def test_unknown(self):
        with patch("normalizer.anthropic.Anthropic") as mock_client:
            mock_client.return_value.messages.create.return_value = make_mock_response("unknown", 0.95, "not a light command")
            r = normalize_command("hello how are you")
            assert r.normalized == "unknown"

    def test_negated(self):
        with patch("normalizer.anthropic.Anthropic") as mock_client:
            mock_client.return_value.messages.create.return_value = make_mock_response("unknown", 0.9, "negated command")
            r = normalize_command("don't turn on the light")
            assert r.normalized == "unknown"
