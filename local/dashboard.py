# local/dashboard.py — web control panel + live cost/latency view.
#
# Reads three cloud endpoints on a timer: /state (live light + recent history),
# /metrics (rolling cost and latency aggregate). Every cloud call degrades to a
# rendered error instead of a 500, so a dead backend still leaves a usable page.
import logging
import os

import requests
from flask import Flask, jsonify, render_template_string, request

CLOUD = os.environ.get("HEY_CINDY_CLOUD", "http://3.234.157.34:8000")
TOKEN = os.environ.get("HEY_CINDY_TOKEN", "cindy-dev-token-123")

REQUEST_TIMEOUT_S = 5

logger = logging.getLogger(__name__)

app = Flask(__name__)

HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <title>Hey Cindy Dashboard</title>
    <style>
      body { font-family: -apple-system, Arial, sans-serif; padding: 24px; max-width: 940px; }
      h2 { margin-bottom: 4px; }
      .sub { color: #666; font-size: 13px; margin-bottom: 20px; }
      .box { padding: 18px 24px; border-radius: 12px; display: inline-block; font-weight: 600; }
      .on { background: #fff3b0; }
      .off { background: #e6e6e6; }
      button { padding: 10px 14px; margin-right: 10px; border-radius: 10px;
               border: 1px solid #999; cursor: pointer; background: #fff; }
      button:hover { background: #f2f2f2; }
      .cards { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 22px; }
      .card { flex: 1 1 150px; box-sizing: border-box; border: 1px solid #e2e2e2;
              border-radius: 12px; padding: 12px 14px; }
      .card .label { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #777; }
      .card .value { font-size: 22px; font-weight: 600; margin-top: 4px; }
      .card .note { font-size: 11px; color: #999; margin-top: 2px; }
      table { border-collapse: collapse; width: 100%; margin-top: 12px; font-size: 13px; }
      th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid #eee; }
      th { color: #666; font-weight: 600; font-size: 11px; text-transform: uppercase; }
      td.num { text-align: right; font-variant-numeric: tabular-nums; }
      .tag { font-size: 11px; padding: 2px 7px; border-radius: 999px; background: #eef; color: #335; }
      .tag.kw { background: #efe; color: #353; }
      .tag.manual { background: #f2f2f2; color: #666; }
      #err { color: #b00; font-size: 13px; margin-top: 12px; min-height: 18px; }
    </style>
  </head>
  <body>
    <h2>Hey Cindy Dashboard</h2>
    <div class="sub">Live light state, per-command latency, and Claude token spend.</div>

    <div id="status" class="box off">Loading...</div>

    <div style="margin-top:16px;">
      <button onclick="sendCmd('on')">ON</button>
      <button onclick="sendCmd('off')">OFF</button>
      <button onclick="toggle()">TOGGLE</button>
    </div>

    <div class="cards">
      <div class="card"><div class="label">Commands</div>
        <div class="value" id="m-count">–</div><div class="note">recent window</div></div>
      <div class="card"><div class="label">Avg latency</div>
        <div class="value" id="m-avg">–</div><div class="note" id="m-p95">p95 –</div></div>
      <div class="card"><div class="label">LLM escalation</div>
        <div class="value" id="m-share">–</div><div class="note" id="m-calls">– calls</div></div>
      <div class="card"><div class="label">Tokens</div>
        <div class="value" id="m-tokens">–</div><div class="note" id="m-io">– in / – out</div></div>
      <div class="card"><div class="label">Est. cost</div>
        <div class="value" id="m-cost">–</div><div class="note">Haiku 4.5 list price</div></div>
    </div>

    <h3 style="margin-top:26px; margin-bottom:0;">Recent commands</h3>
    <table>
      <thead>
        <tr><th>Time</th><th>Heard</th><th>Cmd</th><th>Source</th>
            <th>Path</th><th class="num">Latency</th><th class="num">Tokens</th><th class="num">Cost</th></tr>
      </thead>
      <tbody id="history"><tr><td colspan="8">Loading…</td></tr></tbody>
    </table>

    <div id="err"></div>

   <script>
    // Sub-millisecond is the keyword fast path; rounding it to '0 ms' reads like missing data.
    const fmtMs = v => (v === null || v === undefined) ? '–'
                     : (v < 1 ? '<1 ms' : Math.round(v) + ' ms');
    const fmtCost = v => '$' + (v || 0).toFixed(5);

    function setError(msg) { document.getElementById('err').innerText = msg || ''; }

    async function sendCmd(cmd) {
      const res = await fetch('/api/command', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ text: cmd })
      });

      let data = {};
      try { data = await res.json(); } catch (e) {}

      if (!res.ok || data.ok === false) {
        setError(data.error || data.detail || 'command failed');
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
      if (!data.ok) setError(data.error || 'toggle failed');
      await refresh();
    }

    function renderHistory(rows) {
      const body = document.getElementById('history');
      if (!rows || !rows.length) {
        body.innerHTML = '<tr><td colspan="8">No commands yet.</td></tr>';
        return;
      }
      body.innerHTML = rows.slice().reverse().map(r => {
        const usedLlm = (r.input_tokens || 0) > 0;
        const tokens = usedLlm ? (r.input_tokens + r.output_tokens) : 0;
        // No latency at all means no NLP ran — a button press, not a classification.
        const ranNlp = r.latency_ms !== null && r.latency_ms !== undefined;
        const path = !ranNlp ? ['manual', 'manual'] : (usedLlm ? ['', 'llm'] : ['kw', 'keyword']);
        return `<tr>
          <td>${(r.timestamp || '').slice(11, 19)}</td>
          <td>${r.raw ? r.raw : '—'}</td>
          <td>${r.normalized}</td>
          <td>${r.source || '—'}</td>
          <td><span class="tag ${path[0]}">${path[1]}</span></td>
          <td class="num">${fmtMs(r.latency_ms)}</td>
          <td class="num">${tokens || '—'}</td>
          <td class="num">${usedLlm ? fmtCost(r.cost_usd) : '—'}</td>
        </tr>`;
      }).join('');
    }

    function renderMetrics(m) {
      document.getElementById('m-count').innerText = m.commands;
      document.getElementById('m-avg').innerText = fmtMs(m.avg_latency_ms);
      document.getElementById('m-p95').innerText = 'p95 ' + fmtMs(m.p95_latency_ms);
      document.getElementById('m-share').innerText = Math.round((m.llm_share || 0) * 100) + '%';
      document.getElementById('m-calls').innerText = m.llm_calls + ' calls';
      document.getElementById('m-tokens').innerText = (m.input_tokens + m.output_tokens);
      document.getElementById('m-io').innerText = m.input_tokens + ' in / ' + m.output_tokens + ' out';
      document.getElementById('m-cost').innerText = fmtCost(m.cost_usd);
    }

    async function refresh() {
      try {
        const [stateRes, metricsRes] = await Promise.all([
          fetch('/api/state', { cache: 'no-store' }),
          fetch('/api/metrics', { cache: 'no-store' })
        ]);
        const state = await stateRes.json();
        const metrics = await metricsRes.json();

        if (state.error) { setError(state.error); return; }
        setError('');

        const el = document.getElementById('status');
        el.innerText = (state.light === 'on') ? 'Light: ON' : 'Light: OFF';
        el.classList.toggle('on', state.light === 'on');
        el.classList.toggle('off', state.light !== 'on');

        renderHistory(state.history);
        if (!metrics.error) renderMetrics(metrics);
      } catch (e) {
        setError('dashboard could not reach its backend: ' + e);
      }
    }

    setInterval(refresh, 1200);
    refresh();
    </script>
  </body>
</html>
"""

AUTH_HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def cloud_get(path: str):
    """GET a cloud endpoint, degrading to a JSON error the page can render."""
    try:
        r = requests.get(f"{CLOUD}{path}", headers=AUTH_HEADERS, timeout=REQUEST_TIMEOUT_S)
        r.raise_for_status()
        return jsonify(r.json())
    except requests.RequestException as e:
        # Full detail to the server log; a short label to the page.
        logger.warning("cloud GET %s failed: %s", path, e)
        return jsonify({"error": f"cloud unreachable ({type(e).__name__})"}), 502


def cloud_post(command: str, source: str = "dashboard", **extra):
    # Cloud's /command expects {"command": "on"|"off", ...}, not {"text": ...}.
    # Dashboard commands carry no NLP metrics — no classification ran.
    return requests.post(
        f"{CLOUD}/command",
        json={"command": command, "raw_text": command, "source": source, **extra},
        headers=AUTH_HEADERS,
        timeout=REQUEST_TIMEOUT_S,
    )


@app.get("/")
def home():
    return render_template_string(HTML)


@app.get("/api/state")
def api_state():
    return cloud_get("/state")


@app.get("/api/metrics")
def api_metrics():
    return cloud_get("/metrics")


@app.post("/api/command")
def api_command():
    payload = request.get_json(force=True)
    text = payload.get("text", "")
    try:
        r = cloud_post(text)
    except requests.RequestException as e:
        return jsonify({"ok": False, "error": f"failed to send command: {e}"}), 502
    return (r.text, r.status_code, {"Content-Type": "application/json"})


@app.route("/api/toggle", methods=["POST"])
def api_toggle():
    # 1) Read the current state from the cloud (/state needs the token too).
    try:
        r = requests.get(f"{CLOUD}/state", headers=AUTH_HEADERS, timeout=REQUEST_TIMEOUT_S)
        r.raise_for_status()
        current = r.json().get("light", "off")
    except requests.RequestException as e:
        return jsonify({"ok": False, "error": f"failed to read cloud state: {e}"}), 502

    # 2) Flip it.
    next_cmd = "off" if current == "on" else "on"

    # 3) Send the new command back to the cloud.
    try:
        r2 = cloud_post(next_cmd, confidence=1.0, reason="dashboard_toggle")
        r2.raise_for_status()
    except requests.RequestException as e:
        return jsonify({"ok": False, "error": f"failed to send toggle command: {e}"}), 502

    return jsonify({"ok": True, "from": current, "to": next_cmd})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=6060, debug=False)
