# J3 spec v2: context proxy (automatic, works even in the middle of a long turn)

STATUS: BUILT BY CLAUDE (~/jarvis-build/ctxproxy/proxy.py, tests/, README.md). Jarvis does not rebuild it.
As built, differences from the text below: KEEP_MARGIN is 6000 (post-compaction size ~11-12k, fewer
compactions); a stale RESUME HERE block is kept AND an auto-summary is added; the warn note is appended to
the last user/tool message (not a separate system message, which Qwen templates may reject); the compacted
note is appended to the first system message; a broken or timed-out stream ends with an SSE error event;
optional client key (CTXPROXY_CLIENT_KEY). README.md is the runbook.
v2.1 (2026-09-25): the first request of a new chat gets a NEW CHAT START note (RESUME HERE block + `git log
--oneline -5` + `git status --short` of ~/jarvis-build) appended to the system message, frozen for that chat
(resumes.json); the compaction note carries the same git facts. Header X-Ctxproxy-No-Resume: 1 or
CTXPROXY_RESUME_NEW_CHATS=0 turns the new-chat note off. The autopilot (~/jarvis-build/autopilot) drives
Builder tasks through this proxy with no one typing "continue".

Goal: Jarvis Builder never overflows and never needs Simon to start a new chat. A small proxy sits between Open WebUI and llama-server and sees EVERY model request, including each round of a tool loop, so it can act mid-turn (a filter only runs when Simon sends a message).

Test-first: ~/jarvis-build/ctxproxy/STRESS-PLAN.md is the full test list and the acceptance gates. This spec is the design; where they disagree, ask Simon.

## Measured facts (2026-09-25)
- n_ctx = 24576 in /props and for each of the 2 slots in /slots. Server runs --parallel 2 --kv-unified.
- NOT known yet: whether the two slots share ONE 24576 pool (so a delegate call running while the chat waits eats the chat's room). Live check P4b answers it; until then assume they share.
- NOT known yet: how many tokens one step at xhigh writes (thinking + answer). The proxy measures it (see Logging).

## Build
~/jarvis-build/ctxproxy/proxy.py (FastAPI + httpx in the venv), tests, a systemd unit file for Simon.
- Listens on 127.0.0.1:8113 for tests; the real unit binds 172.17.0.1:8090 so the Open WebUI container can reach it. Unit: After=docker.service llama-server's unit, Wants=docker.service, Restart=always, RestartSec=3.
- Forwards everything to http://127.0.0.1:8080 unchanged (GET /v1/models, /health, /props, /tokenize, auth headers), streaming (SSE) chunk by chunk, no buffering. Timeouts are settings (default 1800 s total, 300 s between chunks).
- All numbers below are settings in one config block at the top of proxy.py, not literals in the code.

## Budget (per request)
- limit = 24576. reserve = output reserve for the model's reply at xhigh (start 6000; set from measured p99 later).
- compact_at = limit - reserve - 1000 (start: 17576). warn_at = compact_at - 3000 (start: 14576).
- count = tokens of ALL message text + the `tools` field (JSON-serialised) + template overhead (start 3%, calibrated in C3). Count via POST /tokenize, 3 s timeout, fallback len(text)//3.

## Actions on POST /v1/chat/completions
1. Skip (forward untouched, log "skip"): background requests. That is: Open WebUI task requests (last user message starts with "### Task:"), any request with header X-Ctxproxy-Skip: 1 (the proxy's own summary call and the delegate plugin set it). Simon also sets Open WebUI's Task Model to the direct 8080 model, so this is a second line of defence.
2. Oversized single message: any one message over 4000 tokens (usually a tool output) is cut to its first 2500 + last 1000 tokens with "[CUT BY CONTEXT PROXY: N tokens removed]" in the middle. This happens on every request, before counting against thresholds.
3. Under warn_at: forward.
4. warn_at to compact_at: append ONE system message at the END: "CONTEXT HIGH (N/24576). Finish the current small step, update the RESUME HERE block in ~/jarvis-build/PROGRESS.md with the exact next action, commit, then continue working. The proxy will compact soon; you will not lose the RESUME HERE block." Never at the start, never twice.
5. At or above compact_at: compact.
   - Handoff text = the RESUME HERE block of ~/jarvis-build/PROGRESS.md (from "## RESUME HERE" to the next "## " heading; max 6000 chars, read with errors="replace"). If the block is missing, empty, or the file's mtime is older than 30 minutes: make ONE summary call direct to 8080 (header X-Ctxproxy-Skip: 1, reasoning_effort low, max_tokens 800, 60 s timeout, prompt trimmed to at most 12000 tokens of the messages being removed) for: goal, done, next action, open problems. Label it "auto-summary, may be incomplete". If that fails too, use "no handoff available; re-check PROGRESS.md and git log".
   - Build: the system message(s) unchanged; then one system message "CONTEXT COMPACTED at N tokens. Earlier messages were removed from your view. Handoff (written <time> Chicago):" + handoff + "Continue from its exact next action. Re-check any fact with a tool before relying on it; do not redo committed work (check git log)." Then the newest whole messages that fit in keep = compact_at - 4000 - (system + tools + note). Always keep the last user message; never split an assistant tool_calls message from ALL its tool results.
   - The note text is frozen at compaction time: no "age: N minutes" or anything else that changes between requests.
6. Sticky state (critical for speed and against thrash). Open WebUI resends the FULL uncompacted history on every request. So the proxy remembers each compaction: key = sha256 of the system message(s) + the first user message; value = the id/index of the first kept message and the frozen note. On later requests with the same key, re-apply the SAME cut and the SAME note byte for byte, and only compact again when the result crosses compact_at again. Keep state in memory plus ~/jarvis-build/ctxproxy/state.json (atomic write) so a proxy restart does not re-compact differently. Max 50 keys, oldest dropped.

## Logging
One JSON line per chat request to ~/jarvis-build/ctxproxy/events.jsonl: time, key (first 8 hex), action (pass/warn/compact/skip/cut/error), tokens before/after, completion_tokens and reasoning tokens if the upstream reports them (final SSE chunk usage/timings), ms added. NEVER message text, headers or secrets. Rotate at 5 MB (keep 1 old file). This log is how we measure the real output per step and set `reserve`.

## Fail open, but never forward an over-limit request
Any exception in counting/compacting: forward the original request (after step 2's cuts) and log the error type. If even that is over limit, return a clear OpenAI-style error message "context proxy: request too large even after cuts" instead of a silent overflow.

## Core tests (full list in STRESS-PLAN.md)
T1 small request forwarded byte-identical, streaming passes. T2 warn band: exactly one CONTEXT HIGH, at the end. T3 compact: fits under compact_at - 4000, last user message present, note present. T4 tool_call pairs never split, parallel calls included. T5 no RESUME HERE block: one summary call with the skip header, then compact. T6 sticky: after a compact, 5 more requests with the growing full history produce an identical prefix (byte compare) and no second compaction until the threshold. T7 forced exception: original forwarded. T8 "### Task:" request skipped. T9 one 30k-token tool output is cut. T10 events.jsonl contains no canary string from messages or headers.

## FOR SIMON (after all automated tests pass)
1. Install the unit (runs as simon).
2. Open WebUI: Admin > Settings > Connections > OpenAI API > +, URL http://172.17.0.1:8090/v1, any key. Point the Jarvis Builder preset's base model at the model from that connection.
3. Admin > Settings > Interface > Task Model: set it to the direct (8080) model.
4. Remove the context_watch filter from the Builder preset only (it counts the full uncompacted history and would tell Jarvis to stop after every compaction). Keep it on plain Jarvis.
5. Plain Jarvis stays direct on 8080. Undo: point Builder back to the direct model, re-add the filter, stop the unit.
