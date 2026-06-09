# local_dashboard.py
import os
import time
import requests
from flask import Flask, jsonify, render_template_string, request

CLOUD = os.environ.get("HEY_CINDY_CLOUD", "http://3.234.157.34:8000")
TOKEN = os.environ.get("HEY_CINDY_TOKEN", "cindy-dev-token-123")

app = Flask(__name__)

HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <title>Hey Cindy Dashboard</title>
    <style>
      body { font-family: Arial, sans-serif; padding: 24px; }
      .box { padding: 18px; border-radius: 12px; display: inline-block; }
      .on { background: #fff3b0; }
      .off { background: #e6e6e6; }
      button { padding: 10px 14px; margin-right: 10px; border-radius: 10px; border: 1px solid #999; cursor: pointer; }
      pre { background: #111; color: #eee; padding: 12px; border-radius: 10px; max-width: 900px; overflow-x: auto; }
    </style>
  </head>
  <body>
    <h2>Hey Cindy Dashboard</h2>

    <div id="status" class="box off">Loading...</div>

    <div style="margin-top:16px;">
      <button onclick="sendCmd('on')">ON</button>
      <button onclick="sendCmd('off')">OFF</button>
      <button onclick="toggle()">TOGGLE</button>
    </div>

   <script>
    async function sendCmd(cmd) {
      const res = await fetch('/api/command', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ text: cmd })
      });

      let data = {};
      try { data = await res.json(); } catch (e) {}

      if (!res.ok || data.ok === false) {
        alert(data.error || data.detail || "command failed");
        return;
      }

      await refresh();
    }

    async function toggle() {
      const res = await fetch('/api/toggle', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({})
      });
      const data = await res.json();
      if (!data.ok) alert(data.error || "toggle failed");
      await refresh();
    }

    async function refresh() {
      const res = await fetch('/api/state', { cache: 'no-store' });
      const data = await res.json();

      const el = document.getElementById('status');
      el.innerText = (data.light === 'on') ? 'Light: ON' : 'Light: OFF';
      el.classList.toggle('on', data.light === 'on');
      el.classList.toggle('off', data.light !== 'on');
    }

    setInterval(refresh, 1200);
    refresh();
    </script>
  </body>
</html>
"""

AUTH_HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def cloud_post(command: str):
    # Cloud's /command expects {"command": "on"|"off", ...}, not {"text": ...}.
    return requests.post(
        f"{CLOUD}/command",
        json={"command": command, "raw_text": command, "source": "dashboard"},
        headers=AUTH_HEADERS,
        timeout=10,
    )

@app.get("/")
def home():
    return render_template_string(HTML)

@app.get("/api/state")
def api_state():
    # /state requires the bearer token too.
    r = requests.get(f"{CLOUD}/state", headers=AUTH_HEADERS, timeout=10)
    r.raise_for_status()
    return jsonify(r.json())

@app.post("/api/command")
def api_command():
    payload = request.get_json(force=True)
    text = payload.get("text", "")
    r = cloud_post(text)
    return (r.text, r.status_code, {"Content-Type": "application/json"})

@app.route("/api/toggle", methods=["POST"])
def api_toggle():
    # 1) 先从云端拿当前状态（/state 需要 token）
    try:
        r = requests.get(f"{CLOUD}/state", headers=AUTH_HEADERS, timeout=2)
        r.raise_for_status()
        data = r.json()
        current = data.get("light", "off")
    except Exception as e:
        return jsonify({"ok": False, "error": f"failed to read cloud state: {e}"}), 502

    # 2) 决定要发 on 还是 off
    next_cmd = "off" if current == "on" else "on"

    # 3) 发给云端
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    try:
        r2 = requests.post(
            f"{CLOUD}/command",
            headers=headers,
            json={"command": next_cmd, "raw_text": "toggle", "confidence": 1.0, "reason": "dashboard_toggle", "source": "dashboard"},
            timeout=2
        )
        r2.raise_for_status()
        return jsonify({"ok": True, "from": current, "to": next_cmd})
    except Exception as e:
        return jsonify({"ok": False, "error": f"failed to send toggle command: {e}"}), 502

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=6060, debug=False)
