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