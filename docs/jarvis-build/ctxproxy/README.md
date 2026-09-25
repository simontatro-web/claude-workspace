# Context proxy (J3 v2.1) and autopilot: install and acceptance runbook

Built and tested by Claude off the box (automated tests for both; counts in step 3). Jarvis does NOT rebuild them.
Everything below is run by Simon on jarvis-1. Steps 1-4 change nothing outside ~/jarvis-build.
The autopilot (Jarvis finishes a task with nobody typing "continue") has its own runbook,
~/jarvis-build/autopilot/README.md, which starts after step 6 here.

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
- The first request of a NEW chat gets a "NEW CHAT START" note appended to the system prompt: the RESUME HERE
  block, `git log --oneline -5` and `git status --short` of ~/jarvis-build. It is frozen for the rest of that
  chat (same bytes every request, so the cache keeps working). A new chat picks up where the last one stopped
  without you pasting anything. The compaction note carries the same git facts.
- Open WebUI's background "### Task:" requests (titles, tags) and requests carrying X-Ctxproxy-Skip pass
  through untouched.
- Fails open on its own bugs, but never forwards a request that cannot fit: that gets a clear error instead.
- Logs one line of numbers per request to events.jsonl (no message text, no headers). report.py reads it.

All thresholds are settings (CTXPROXY_* environment variables; see Config at the top of proxy.py). The
defaults assume replies of up to ~6,000 tokens at xhigh (RESERVE). report.py tells you the real number.

## 1. Put the files on the box
On your Windows PC: open the repo on GitHub (branch claude/orchestrator-research), go to
docs/jarvis-build/jarvis-build-bundle.tgz, click "Download raw file". Then in PowerShell:

    scp $HOME\Downloads\jarvis-build-bundle.tgz simon@jarvis-2:~/

On jarvis-1:

    sha256sum ~/jarvis-build-bundle.tgz
    tar -xzvf ~/jarvis-build-bundle.tgz -C ~/jarvis-build && cd ~/jarvis-build && git status --short

The checksum must match the one Claude gave you. The tar adds ctxproxy/ and autopilot/ files and replaces
handoff/00-START-HERE.md, 01-steps.md, 07-builder-prompt.md and 09-spec-context-compactor.md. It does not
touch STRESS-PLAN.md.

## 2. Python packages (into the jarvis-build venv only)

    ~/jarvis-build/venv/bin/pip install starlette uvicorn httpx pytest

## 3. Automated suites (fake servers, 127.0.0.1 only, about 2 minutes)

    cd ~/jarvis-build && venv/bin/python -m pytest -q -p no:cacheprovider ctxproxy/tests autopilot/tests

Expect `195 passed` (64 proxy + 131 autopilot). Anything else: stop and paste the output to Claude.

## 4. Real-server smoke test (uses llama-server for 1-3 minutes; changes nothing)
Do this when no Jarvis chat is running.

    cd ~/jarvis-build && venv/bin/python ctxproxy/smoke_real.py

Expect `8/8 passed`. It checks passthrough, streaming, count accuracy against llama-server's own count
(within 5%), that the chat template accepts the warn note and the compacted request, that the prompt cache is
reused after compaction, and that the new-chat note is accepted and reused. Paste the whole output to Claude
either way; the numbers matter. If it says the test proxy could not start, something already uses port 8113.

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
5. Paste the Builder prompt v2 (between the lines of ~/jarvis-build/handoff/07-builder-prompt.md) into the
   preset's system prompt, replacing v1. Keep Function Calling: Native.
Test: start a NEW Builder chat and send: "Run `git -C ~/jarvis-build log --oneline -1` with your shell tool and
quote the output. Then tell me the exact next action from your NEW CHAT START note." Then:

    tail -3 ~/jarvis-build/ctxproxy/events.jsonl

Expect "action": "resume" with "resume": "new" on the first line, "sticky" on the tool-loop lines after it,
and Jarvis quoting a real commit and your RESUME HERE next action.
Undo: point Builder back at the direct model, paste the v1 prompt back (git history of 07-builder-prompt.md),
turn the filter back on.

## 7. Acceptance (the gates in STRESS-PLAN.md). All runs at reasoning effort xhigh.
The main gates run through the autopilot, with nobody typing: autopilot/README.md section 5 (AP-1 to AP-4).
This section proves the Open WebUI chat path too. One run in a NEW Builder chat:

    python3 ~/jarvis-build/ctxproxy/live/setup_task.py --reset

Paste to Jarvis:

> Acceptance run. Read ~/ctxtest/TASK.md and follow it exactly, and keep going until all 25 edits are committed. If you see CONTEXT HIGH, update RESUME HERE and keep going. If you see CONTEXT COMPACTED, run `git -C ~/ctxtest log --oneline | head -3` before anything else and continue from the next uncommitted edit. Every claim you make must quote the command output that proves it.

If Jarvis stops before 25 (Open WebUI can end a long tool loop), reply `continue` and count how many times you
had to. When he says done:

    python3 ~/jarvis-build/ctxproxy/live/check_task.py
    ~/jarvis-build/venv/bin/python ~/jarvis-build/ctxproxy/report.py --since-min 240

- Chat gate: PASS with at least 1 compaction. Scan the chat: any claim without its command output counts as a
  failure. (The three-run gates 2 and 4 are the autopilot's AP-1.)
- Gate 3 (new chat picks up by itself): one more chat run where you close the chat after about edit 12, open a
  new Builder chat and send only "Continue." The NEW CHAT START note must be enough. It must PASS.
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
