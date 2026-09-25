cd ~/jarvis-build/handoff
cat > 00-START-HERE.md <<'JBH_END'
# Jarvis build mission (from Simon, written by Claude, 2026-09-25)

Simon is out of Claude usage. You (Jarvis) build the first pieces of his orchestrator plan yourself, one small step per chat, while he supervises. Call him Simon.

## Every chat, in this order
1. Read this file, then ~/jarvis-build/PROGRESS.md (create it if missing), then 01-steps.md.
2. Take the FIRST unfinished step in 01-steps.md and read its spec file.
3. Tell Simon in 3-5 lines what you will build and how you will test it. Wait for his OK.
4. Build it in ~/jarvis-build/<step>/. Use write_file for any multi-line file (never heredocs). Keep each file small.
5. Run its tests. Paste the real test output summary; never claim a pass you did not see.
6. Commit: ~/jarvis-build is a git repo (git init it on first use). One commit per working change.
7. Update PROGRESS.md: done / test result / next / FOR SIMON (commands he must run, each with a test and an undo).
8. Stop when the step is done or the chat is getting long (about 15 tool calls). Simon starts a fresh chat for the next step.

## Hard rules (these protect the server you run on)
- NEVER run: sudo, apt, snap, lxc, lxd, docker, pkill, killall, reboot, shutdown.
- NEVER start, stop, restart or edit any systemd unit. Never touch llama-server, Open WebUI, the tool server (~/jarvis-tools), ~/.config/jarvis, ~/bench, ~/models, /etc.
- Only kill a process you started yourself in this step, by the PID you recorded.
- Test servers bind to 127.0.0.1 only, ports 8110-8119.
- Python: use a venv at ~/jarvis-build/venv (python3 -m venv). pip install only into that venv.
- Anything that needs root: write the exact commands under FOR SIMON in PROGRESS.md, with what it changes, a test, and an undo. Simon runs them after checking.
- Loops: if the same fix fails 3 times, stop and write down exactly what is failing. Max 10 tool calls per turn.
- Facts about the box: check with a read-only command, do not guess. Say "measured" or "not checked".
- Never do Simon's graded schoolwork.

## What the finished plan looks like (for context only)
A job queue in SQLite that refuses to run any build job without a spec Simon approved; workers that run jobs with hard caps; a kill switch; approvals from his phone; health alerts; nightly off-box backups. The full design is in the Claude repo (docs/orchestrator-research.md, docs/orchestrator-roadmap.md); you do not need it to do your step.

## Checkpoint rule (added by Simon; read this first)
Your context is only 24,576 tokens and you cannot see how full it is.
- Keep a block at the TOP of ~/jarvis-build/PROGRESS.md titled "RESUME HERE" (max 15 lines): current step, what is done, the exact next action, open problems, files touched.
- Rewrite it after EVERY finished sub-task (a test passing, a commit), not only at the end.
- If a system message says CONTEXT NEARLY FULL or CONTEXT CRITICAL (the filter, used before the J3 proxy exists): update RESUME HERE, commit, tell Simon to start a new chat, and stop.
- If a system message says CONTEXT HIGH (the J3 proxy): finish the current small step, update RESUME HERE, commit, then keep working.
- If a system message says CONTEXT COMPACTED: earlier messages are gone from your view. Continue from the handoff's exact next action. Check `git log --oneline -5` before redoing anything, and re-check any fact with a tool before stating it.
- A new chat reads RESUME HERE first and continues from its "exact next action".
JBH_END
cat > 01-steps.md <<'JBH_END'
# Build steps, in order (Jarvis builds; Simon runs anything needing root)

Status lives in ~/jarvis-build/PROGRESS.md, not here.

| Step | What | Spec | Who installs |
|---|---|---|---|
| S1 | Backup script (restic, SQLite-safe), tested against a local test repo | 02-spec-backup.md | Simon installs the timer and the real target later |
| S1b | Context-watch filter for Open WebUI (warns before the context overflows) | 05-spec-context-filter.md | Simon pastes it into Open WebUI |
| J1 | Jarvis Builder preset: system prompt, reply cap, filter | 07-builder-prompt.md | Simon (Open WebUI settings) |
| J2 | delegate tool: fresh-context thinking | 08-spec-delegate-tool.md | Jarvis via create_tool |
| J2b | delegate fix-up: 8000 cap, empty answer at cap, ~ paths, log location | 08-spec-delegate-tool.md (J2b section) | Jarvis via create_tool |
| J2c | Live check P4b: do the two slots share one KV pool? | 08-spec-delegate-tool.md (J2c section) | Simon drives, Jarvis records |
| J4 | replace_in_file tool: exact small edits without shell quoting | 10-spec-edit-tool.md | Jarvis via create_tool; Simon adds one line to the Builder prompt |
| J3 | Context proxy v2: warn + sticky compact on every model request, mid-turn included; built test-first against ctxproxy/STRESS-PLAN.md | 09-spec-context-compactor.md | Jarvis builds; Simon installs the unit and the Open WebUI settings |
| B1 | Backup to the USB model drive (config.real.env, remount rw/ro in the unit, FOR SIMON) | Simon's message; use delegate for the mount-namespace question | Simon runs FOR SIMON |
| S2 | Health watchdog (alerts when something is MISSING), dry-run tested | 03-spec-watchdog.md | Simon installs the unit |
| S3 | Job database + job API with the spec-approval gate, tested on 127.0.0.1:8111 | 04-spec-jobdb.md | Simon installs the unit later |
| S4 | Worker v0: claims approved jobs, echo type only, pause flag, caps | Write a spec draft into PROGRESS.md first; Simon approves before you build | Simon |

After S4, stop and tell Simon the foundation is ready for Claude to review.

## Simon-only items (do NOT attempt these; they need root)
- Remove simon from the lxd group, purge lxd-installer.
- Hold the NVIDIA driver packages.
- Bind the tool server to 172.17.0.1 and add a firewall.
- Create the separate jarvis / jarvis-core / jarvis-eval users.
- The off-box backup account (Backblaze B2) and storing the restic password off the box.
- Installing any systemd unit or timer you write.
JBH_END
cat > 08-spec-delegate-tool.md <<'JBH_END'
# J2 spec: delegate tool (fresh-context thinking for Jarvis)

Why: your chat window is small and your own thinking fills it. delegate sends a self-contained brief to a FRESH model call; only the answer comes back into your chat. This is the one step allowed to use create_tool.

Before writing: read one existing plugin in ~/jarvis-tools/plugins (e.g. gpu_status) and copy its exact pattern (endpoint decorator, auth dependency, pre-injected names that must NOT be imported).

Endpoint: POST /delegate, operation_id "delegate", same auth as the other plugins. Body:
- task (str, required): the full brief. The fresh model sees ONLY this plus the files.
- files (list of paths, optional, max 4): each read as first 6000 + last 2000 chars, with a marker if cut.
- effort (low|medium|xhigh, default medium)
- max_output_tokens (default 4000, max 16000; includes the model's thinking. At xhigh use 12000-16000: 8000 was measured to end with no answer)

What it does:
1. Build messages: system = "You are a focused expert helper for Simon's server jarvis-1. Answer only the task, concretely. If the files do not contain what you need, say exactly what is missing. Never invent file contents or command output." user = task + the files, each under a "=== FILE: path ===" header.
2. Size check: POST the text to http://127.0.0.1:8080/tokenize. Refuse with a clear error if it exceeds 10000 tokens.
3. POST http://127.0.0.1:8080/v1/chat/completions with messages, temperature 0, max_tokens, chat_template_kwargs {"reasoning_effort": effort}. Timeout 900 s.
4. Return {answer, prompt_tokens, completion_tokens, seconds, finish_reason, files_cut}. answer = message content only, NEVER reasoning_content, passed through _clip.
5. One delegate at a time: a module-level lock; a second call while one runs returns {"error": "busy"} immediately.
6. Append one JSON line per call to /home/simon/jarvis-build/logs/delegate-log.jsonl (time, effort, max_tokens, tokens, seconds, finish_reason). Never task or file text.

Tests: after create_tool, delegate appears as one of your own tools (Open WebUI reads the tool list live). Call it as a tool; never read ~/.config/jarvis to curl it. Paste results:
- T1: task "What is 17*23? Answer with the number only." -> answer contains 391, no thinking text in answer.
- T2: files=[a small test file you create] and a question about its contents -> the answer uses them.
- T3: a task padded past 10000 tokens -> refused with the size error, no model call.
- T4: two calls at once -> exactly one "busy". If you cannot make two calls at once, quote the lock code instead and say T4 was not run.
- T5: after T1, check the llama-server log line for Simon's next chat turn (prompt eval tokens and ms) and record it in PROGRESS.md: this measures whether a delegate call pushes Simon's chat out of the shared cache (VERIFY item).

FOR SIMON: nothing to install (create_tool restarts the tool server by itself, about 3 s without tools). Tell him if T5 shows his next chat turn re-reading its whole history.

## J2b fix-up (found 2026-09-25: two xhigh calls came back empty)
Cause, measured: `_MAX_OUTPUT_TOKENS = 8000` at line 16 of the plugin silently caps every call; at xhigh the model spends all 8000 on thinking and never answers.
Back up the plugin first, then:
- (a) raise the cap to 16000; the requested value is sent as asked (up to the cap), never silently lowered.
- (b) finish_reason "length" with empty answer -> return {"error": "hit max_tokens=<n> with no answer (effort=<e>); retry with a bigger max_output_tokens or a smaller task"}. Never an empty success.
- (c) os.path.expanduser on every file path; paths outside /home/simon are refused with a clear error.
- (d) log moves to ~/jarvis-build/logs/ (metadata only, as in step 6); add logs/ to ~/jarvis-build/.gitignore.
- (e) send header X-Ctxproxy-Skip: 1 on its model request (harmless now; matters if it ever goes through the J3 proxy).
- (f) move delegate-oversized.txt and delegate-test-file.txt from ~/jarvis-build to ~/jarvis-build/delegate/tests/; copy the plugin into ~/jarvis-build/delegate/ so it is in git.
Tests: T6 a 16000 request is sent with max_tokens 16000 (read it from the log line). T7 a cap hit (effort xhigh, max_output_tokens 300, a hard question) returns the error text. T8 a "~/..." path works. T9 the log has no task text (grep for a canary word you put in the task). End with `git status --short` clean.

## J2c live check P4b (needs Simon; do right after J2b)
Question: do the two slots share one 24576-token KV pool?
1. Simon, in a Builder chat that is already long (Open WebUI shows ~15k+ tokens, or after ~12 tool calls), asks Jarvis to call delegate at effort xhigh, max_output_tokens 12000, on a hard question.
2. Then sends one short normal message in the same chat.
3. Jarvis reads the llama-server log lines for those requests (prompt eval tokens and ms, any "context"/"KV"/"failed" line) and records in PROGRESS.md: did the delegate call finish; did the next chat turn re-read its whole history (prompt eval tokens close to the full chat size = evicted); any error.
Result decides J3's numbers: if evicted or failed, delegate must be capped to what is left of the pool, and J3's reserve grows.
JBH_END
cat > 09-spec-context-compactor.md <<'JBH_END'
# J3 spec v2: context proxy (automatic, works even in the middle of a long turn)

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
JBH_END
cat > 10-spec-edit-tool.md <<'JBH_END'
# J4 spec: replace_in_file tool (small exact edits without shell quoting)

Why: editing two lines of PROGRESS.md cost a long stretch of xhigh thinking about sed/python quoting. That thinking fills your context. This tool makes an exact edit in one call.

Build with create_tool, same pattern as the delegate plugin (read it first; copy its endpoint decorator and auth; do not import pre-injected names). Copy the finished plugin into ~/jarvis-build/edittool/ so it is in git.

Endpoint: POST /replace_in_file, operation_id "replace_in_file". Body:
- path (str): expanduser; must be inside /home/simon/jarvis-build or /home/simon/jarvis-tools/plugins, else refuse. Resolve symlinks before the check.
- old (str): exact text to find. Empty old is allowed only with mode "append".
- new (str): replacement text.
- mode: "replace" (default) | "insert_after" (insert new right after old) | "append" (add new at end of file).
- expect (int, default 1): how many times old must occur. If the real count differs, change nothing and return {"error": "old found N times, expected M", "hint": first 3 line numbers where it occurs}.

What it does:
1. Read the file as UTF-8 (refuse binary or >2 MB).
2. Backup to ~/jarvis-build/.backups/<relative path>.<timestamp> before writing; add .backups/ to .gitignore.
3. Write atomically (temp file in the same dir + os.replace), keep the file's permissions.
4. Return {ok, path, replaced, backup, preview}: preview = up to 6 lines around the first change, never the whole file.
5. No shell, no subprocess.

Tests (call it as a tool, paste results):
- T1 replace a unique line in a test file under ~/jarvis-build/edittool/tests/ -> ok, file changed, backup exists.
- T2 old occurring twice with expect 1 -> error, file unchanged (compare sha256 before/after).
- T3 path /etc/hosts and a symlink in ~/jarvis-build pointing to /etc/hosts -> both refused.
- T4 insert_after under "## RESUME HERE" in a copy of PROGRESS.md -> line inserted in the right place.
- T5 text with quotes, $, backslashes and an em dash -> written exactly (sha256 of expected vs actual).

After J4, the Builder prompt rule: use replace_in_file for edits to existing files; write_file only for new files or full rewrites.

FOR SIMON: nothing to install. Add the rule line above to the Builder preset system prompt.
JBH_END
for f in 00-START-HERE.md 01-steps.md 08-spec-delegate-tool.md 09-spec-context-compactor.md 10-spec-edit-tool.md; do echo "$f $(wc -l < $f) $(sha256sum $f | cut -c1-16)"; done; git -C ~/jarvis-build add handoff; git -C ~/jarvis-build commit -q -m "Handoff: J3 v2 spec, J2b/J2c delegate fix-up, J4 edit tool"; git -C ~/jarvis-build log --oneline -1; cd ~
