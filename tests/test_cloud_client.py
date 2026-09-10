from unittest.mock import patch, MagicMock
from local.cloud_client import send_command

class TestSendCommand:

    @patch("local.cloud_client.requests.post")
    def test_success_on(self, mock_post):
        mock_post.return_value = MagicMock(
            ok=True,
            status_code=200,
            json=lambda: {"status": "ok"}
        )
        result = send_command("on")
        assert result["ok"] is True
        assert result["status_code"] == 200

    @patch("local.cloud_client.requests.post")
    def test_http_error(self, mock_post):
        mock_post.return_value = MagicMock(
            ok=False,
            status_code=401,
            json=lambda: {"detail": "Unauthorized"}
        )
        result = send_command("on")
        assert result["ok"] is False
        assert result["error"] == "http_error"

    @patch("local.cloud_client.requests.post")
    def test_timeout(self, mock_post):
        import requests
        mock_post.side_effect = requests.Timeout()
        result = send_command("on")
        assert result["ok"] is False
        assert result["error"] == "timeout"

    @patch("local.cloud_client.requests.post")
    def test_payload_contains_command(self, mock_post):
        mock_post.return_value = MagicMock(
            ok=True, status_code=200,
            json=lambda: {}
        )
        send_command("off", raw_text="turn off", confidence=0.9)
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs["json"]
        assert payload["command"] == "off"
        assert payload["confidence"] == 0.9

    @patch("local.cloud_client.requests.post")
    def test_payload_carries_instrumentation(self, mock_post):
        mock_post.return_value = MagicMock(ok=True, status_code=200, json=lambda: {})
        send_command("on", latency_ms=412.5, input_tokens=180, output_tokens=42)
        payload = mock_post.call_args.kwargs["json"]
        assert payload["latency_ms"] == 412.5
        assert payload["input_tokens"] == 180
        assert payload["output_tokens"] == 42

    @patch("local.cloud_client.requests.post")
    def test_non_json_error_body_is_surfaced_as_text(self, mock_post):
        def boom():
            raise ValueError("not json")
        mock_post.return_value = MagicMock(
            ok=False, status_code=502, text="<html>bad gateway</html>", json=boom)
        result = send_command("on")
        assert result["ok"] is False
        assert result["response"]["detail"] == "<html>bad gateway</html>"

    @patch("local.cloud_client.requests.post")
    def test_non_json_success_body_is_surfaced_as_text(self, mock_post):
        def boom():
            raise ValueError("not json")
        mock_post.return_value = MagicMock(
            ok=True, status_code=200, text="OK", json=boom)
        result = send_command("on")
        assert result["ok"] is True
        assert result["data"]["detail"] == "OK"

    @patch("local.cloud_client.requests.post")
    def test_connection_error(self, mock_post):
        import requests
        mock_post.side_effect = requests.ConnectionError("EC2 unreachable")
        result = send_command("on")
        assert result["ok"] is False
        assert result["error"] == "request_exception"
        assert "EC2 unreachable" in result["message"]
