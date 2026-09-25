# Context proxy (J3): install and acceptance runbook

Built and tested by Claude off the box (51 automated tests, 3 clean runs in a row). Jarvis does NOT rebuild it.
Everything below is run by Simon on jarvis-1. Steps 1-4 change nothing outside ~/jarvis-build.

## What it does
Open WebUI -> proxy (172.17.0.1:8090) -> llama-server (127.0.0.1:8080). On every model request, including each
tool-loop round, it counts prompt + tool schemas:
- under 14,576 tokens: passes the request through byte for byte.
- 14,576 to 17,575: appends one "CONTEXT HIGH" note to the last message (save RESUME HERE, commit, keep working).
- 17,576 or more: compacts. The system prompt stays, plus one frozen "CONTEXT COMPACTED" note containing the
  RESUME HERE block of ~/jarvis-build/PROGRESS.md (or an auto-summary if the block is missing or older than
  30 min), the turn's user message, and the newest whole messages. The result is about 11-12k tokens.
- After a compaction it repeats the same cut and the same note on every later request (Open WebUI keeps
  sending the full history), so llama-server's prompt cache keeps working and it does not compact every step.
- Any single message over 4,000 tokens (a huge tool output) is cut to its first 2,500 + last 1,000 tokens
  with a marker.
- Open WebUI's background "### Task:" requests (titles, tags) and requests carrying X-Ctxproxy-Skip pass
  through untouched.
- Fails open on its own bugs, but never forwards a request that cannot fit: that gets a clear error instead.
- Logs one line of numbers per request to events.jsonl (no message text, no headers). report.py reads it.

All thresholds are settings (CTXPROXY_* environment variables; see Config at the top of proxy.py). The
defaults assume replies of up to ~6,000 tokens at xhigh (RESERVE). report.py tells you the real number.

## 1. Put the files on the box
On your Windows PC: open the repo on GitHub (branch claude/orchestrator-research), go to
docs/jarvis-build/ctxproxy-bundle.tgz, click "Download raw file". Then in PowerShell:

    scp $HOME\Downloads\ctxproxy-bundle.tgz simon@jarvis-2:~/

On jarvis-1:

    sha256sum ~/ctxproxy-bundle.tgz
    tar -xzvf ~/ctxproxy-bundle.tgz -C ~/jarvis-build && cd ~/jarvis-build && git status --short

The checksum must match the one Claude gave you. The tar adds ctxproxy/ files and replaces
handoff/01-steps.md and handoff/09-spec-context-compactor.md. It does not touch STRESS-PLAN.md.

## 2. Python packages (into the jarvis-build venv only)

    ~/jarvis-build/venv/bin/pip install starlette uvicorn httpx pytest

## 3. Automated suite (fake llama-server, 127.0.0.1 only, about 1 minute)

    cd ~/jarvis-build && venv/bin/python -m pytest -q ctxproxy/tests

Expect `51 passed`. Anything else: stop and paste the output to Claude.

## 4. Real-server smoke test (uses llama-server for 1-3 minutes; changes nothing)
Do this when no Jarvis chat is running.

    cd ~/jarvis-build && venv/bin/python ctxproxy/smoke_real.py

Expect `6/6 passed`. It checks passthrough, streaming, count accuracy against llama-server's own count
(within 5%), that the Qwen chat template accepts the warn note and the compacted request, and that the
prompt cache is reused after compaction. Paste the whole output to Claude either way; the numbers matter.

## 5. Install the service (root)
Check whether llama-server needs a key: `curl -s -o /dev/null -w '%{http_code}\n' localhost:8080/v1/models`
(200 = no key; 401 = it needs one, put it in CTXPROXY_UPSTREAM_KEY below).

    umask 077; mkdir -p ~/.config
    printf 'CTXPROXY_CLIENT_KEY=%s\n' "$(openssl rand -hex 24)" > ~/.config/jarvis-ctxproxy.env
    # only if the curl above said 401:  echo 'CTXPROXY_UPSTREAM_KEY=<the llama-server key>' >> ~/.config/jarvis-ctxproxy.env
    sudo install -m 644 ~/jarvis-build/ctxproxy/ctxproxy.service /etc/systemd/system/jarvis-ctxproxy.service
    sudo systemctl daemon-reload && sudo systemctl enable --now jarvis-ctxproxy
    systemctl status jarvis-ctxproxy --no-pager | head -5
    curl -s http://172.17.0.1:8090/ctxproxy/health

Test: health prints `{"ok":true,"compact_at":17576,"warn_at":14576,...}`. Then check the Open WebUI container can reach it:

    sudo docker exec open-webui python3 -c "import urllib.request;print(urllib.request.urlopen('http://172.17.0.1:8090/ctxproxy/health').read())"

If that times out, a firewall is blocking docker -> host port 8090; paste the output to Claude.
Undo: `sudo systemctl disable --now jarvis-ctxproxy && sudo rm /etc/systemd/system/jarvis-ctxproxy.service && sudo systemctl daemon-reload`.

## 6. Open WebUI (only the Builder preset changes; plain Jarvis stays direct on 8080)
1. Admin > Settings > Connections > OpenAI API > +: URL `http://172.17.0.1:8090/v1`, key = the value after
   `CTXPROXY_CLIENT_KEY=` in ~/.config/jarvis-ctxproxy.env (`cat` it). Save; the model list should load.
2. Workspace > Models > Jarvis Builder: set its base model to the model from that new connection.
3. Admin > Settings > Interface > Task Model: set it to the direct (8080) model, so title/tag requests skip the proxy.
4. In the Jarvis Builder preset, turn OFF the context_watch filter (it counts the full uncompacted history and
   would tell Jarvis to stop after every compaction). Leave it on for plain Jarvis.
Test: start a Builder chat, say "hi", then `tail -1 ~/jarvis-build/ctxproxy/events.jsonl` shows a new line.
Undo: point Builder back at the direct model and turn the filter back on.

## 7. Acceptance (the gates in STRESS-PLAN.md). All runs at reasoning effort xhigh.
Run A, one at a time, each in a NEW Builder chat:

    python3 ~/jarvis-build/ctxproxy/live/setup_task.py --reset

Paste to Jarvis:

> Acceptance run. This task overrides the 10-tool-calls-per-turn rule: keep going in this turn until all 25 edits are committed or you are truly blocked. Read ~/ctxtest/TASK.md and follow it exactly. If you see CONTEXT HIGH, update RESUME HERE and keep going. If you see CONTEXT COMPACTED, run `git -C ~/ctxtest log --oneline | head -3` before anything else and continue from the next uncommitted edit. Every claim you make must quote the command output that proves it.

If Jarvis stops before 25 (Open WebUI can end a long tool loop), reply `continue` in the same chat. When he says done:

    python3 ~/jarvis-build/ctxproxy/live/check_task.py
    ~/jarvis-build/venv/bin/python ~/jarvis-build/ctxproxy/report.py --since-min 240

- Gate 2: three runs print PASS, each with at least 1 compaction (gate 4: at least one run with 2 or more).
  Also scan the chat: any claim without its command output counts as a failure.
- Gate 3: one more run where you close the chat after about edit 12, open a new Builder chat and say
  "Read ~/jarvis-build/PROGRESS.md RESUME HERE and continue the acceptance task in ~/ctxtest." It must PASS.
- Gate 5 (P4b): in a Builder chat that is already past ~15k tokens (report.py shows it, or after a
  compaction), ask Jarvis to call delegate at effort xhigh with max_output_tokens 12000 on a hard question,
  then send one short message. `report.py --since-min 10` must show no errors, and the next chat request
  must not re-read its whole prompt.
Paste every check_task.py and report.py output to Claude. Until all gates pass, the manual new-chat routine
stays the official fallback.

## Tuning after the runs
report.py prints "suggested CTXPROXY_RESERVE" from the real reply lengths and the count accuracy. To change a
setting: add it to ~/.config/jarvis-ctxproxy.env (e.g. `CTXPROXY_RESERVE=5000`) and
`sudo systemctl restart jarvis-ctxproxy`. If the count accuracy says it under-counts by more than 2%, raise
CTXPROXY_OVERHEAD_PCT by that amount.
