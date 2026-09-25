# S2 spec: health watchdog

Goal: tell Simon when something that should be running is ABSENT. Alerts on changes only (down once, recovered once), never spam.

Files: ~/jarvis-build/watchdog/watchdog.py (stdlib + urllib only), config.json, state.json (written by the script).

config.json:
- checks: list of {name, type, target, ...}. Types:
  - http: GET target, pass if status == expect (default 200) within timeout 5 s
  - disk_free: path, min_gb
  - file_age: path, max_hours (for the backup STATUS_FILE; also fail if its "ok" is false)
  - systemd_active: unit name, uses `systemctl is-active` (read-only, allowed)
- notify: {"type": "ntfy", "url": "https://ntfy.sh", "topic": "SIMON_FILLS_THIS"} or {"type": "print"}
- Real checks Simon wants: llama-server http://127.0.0.1:8080/health; Open WebUI http://127.0.0.1:3000/ ; tool server http://127.0.0.1:8200/openapi.json (Simon will change it to http://172.17.0.1:8200/openapi.json after the bind fix); disk_free / min 25 GB; file_age backup status 26 h; systemd_active llama-server, jarvis-run-host-commands.

Behaviour:
- Modes: --once (one cycle, for tests) and default loop every 60 s.
- First cycle: send one DOWN for each check that is already failing; say nothing about passing checks.
- On a check going pass->fail: one alert "DOWN: name: reason". fail->pass: one alert "RECOVERED: name". Unchanged: nothing.
- state.json written atomically (write tmp, rename), so a restart does not re-alert.
- Every cycle wrapped in try/except: one broken check never kills the loop; a check that raises counts as failed with the error text.
- ntfy send: POST to url/topic with the message; priority 5 for DOWN, 3 for RECOVERED. Failure to send is logged, not fatal.

Tests (use notify type print; paste output):
- T1: one http check to 127.0.0.1:8119 (nothing listening). --once: exactly one DOWN. --once again: nothing. Start a tiny test server (python3 -m http.server 8119 --bind 127.0.0.1, record its PID). --once: exactly one RECOVERED.
- T2: with the test server up, delete state.json, --once: nothing; kill ONLY your recorded PID; --once: exactly one DOWN; --once again: nothing; restart server; --once: exactly one RECOVERED.
- T3: disk_free with min_gb 999999: fails with a clear reason.
- T4: a check type that raises (bad config): loop survives, reported as failed.

FOR SIMON when done: the systemd unit text (runs as simon for now, Restart=always, NOT part of any autonomy target), and how to put his ntfy topic in config.json.
