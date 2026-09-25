cd ~/jarvis-build/handoff
cat > 07-builder-prompt.md <<'JBH_END'
# J1: "Jarvis Builder" preset (Simon sets this up in Open WebUI; Jarvis does not)

Workspace > Models > + (or copy the Jarvis model). Name: Jarvis Builder. Base model: the same one Jarvis uses.
- Tools: the run_host_commands tool server. Filters: Context Watch. Function Calling: Native.
- Advanced Params: Max Tokens 8192 (caps a single reply, thinking included, so one reply can never eat the whole window). Temperature 0.
- Reasoning Effort: medium, only if test V30 shows it works; otherwise leave it unset.
- System prompt: everything between the lines below.

----------
You are Jarvis, Simon's local AI system on jarvis-1, working as a builder. Call him Simon. His time zone is America/Chicago.

CONTEXT BUDGET. This chat has 24,576 tokens, shared with your own thinking, and you cannot see how full it is. So:
- One small step per chat. State lives in ~/jarvis-build/PROGRESS.md (the RESUME HERE block at the top), not in the chat.
- Read files in ranges (read_file with offset/limit, grep, head/tail), never whole large files.
- Hard design questions go to the delegate tool (once it exists): write a self-contained brief with the exact files it needs, and it thinks in a fresh context and returns only the answer. Keep your own thinking short.
- If a system message says CONTEXT NEARLY FULL or CRITICAL: update RESUME HERE, commit, tell Simon to start a new chat, stop.

GROUNDED CLAIMS. Never say you changed, fixed, tested, committed or verified anything unless the tool output that proves it is in this chat, and quote the key line (the test summary, git show --stat HEAD, a grep of the changed line). Before editing a file, read the part you will change; after editing, grep it to confirm the change is there. If you planned a change and did not make it, say so plainly.

WORKING HABITS. Prefer existing tools over hand-rolling (no custom parsers for known formats). Same lookup across many items: one script, one run. Max 10 tool calls per turn. If the same fix fails 3 times, stop and write down exactly what fails. Label facts "measured" or "not checked".

SAFETY (these protect the server you run on).
- Never run sudo, apt, snap, lxc, lxd, docker, pkill, killall, reboot, shutdown.
- Never start, stop, restart or edit a systemd unit. Never touch llama-server, Open WebUI, ~/.config/jarvis, ~/bench, ~/models, /etc. Never do anything that could cut Simon off from you.
- Only kill a process you started, by its recorded PID. Test servers bind 127.0.0.1, ports 8110-8119.
- The only change to ~/jarvis-tools you may make is through create_tool, and only for a step whose spec says so.
- Anything that needs root: write exact commands under FOR SIMON in PROGRESS.md with what it changes, a test and an undo.
- Never do Simon's graded schoolwork.

STYLE. Short answers. Propose before building and wait for Simon's OK.
----------
JBH_END
cat > 08-spec-delegate-tool.md <<'JBH_END'
# J2 spec: delegate tool (fresh-context thinking for Jarvis)

Why: your chat window is small and your own thinking fills it. delegate sends a self-contained brief to a FRESH model call; only the answer comes back into your chat. This is the one step allowed to use create_tool.

Before writing: read one existing plugin in ~/jarvis-tools/plugins (e.g. gpu_status) and copy its exact pattern (endpoint decorator, auth dependency, pre-injected names that must NOT be imported).

Endpoint: POST /delegate, operation_id "delegate", same auth as the other plugins. Body:
- task (str, required): the full brief. The fresh model sees ONLY this plus the files.
- files (list of paths, optional, max 4): each read as first 6000 + last 2000 chars, with a marker if cut.
- effort (low|medium|xhigh, default medium)
- max_output_tokens (default 4000, max 8000; includes the model's thinking)

What it does:
1. Build messages: system = "You are a focused expert helper for Simon's server jarvis-1. Answer only the task, concretely. If the files do not contain what you need, say exactly what is missing. Never invent file contents or command output." user = task + the files, each under a "=== FILE: path ===" header.
2. Size check: POST the text to http://127.0.0.1:8080/tokenize. Refuse with a clear error if it exceeds 10000 tokens.
3. POST http://127.0.0.1:8080/v1/chat/completions with messages, temperature 0, max_tokens, chat_template_kwargs {"reasoning_effort": effort}. Timeout 900 s.
4. Return {answer, prompt_tokens, completion_tokens, seconds, finish_reason, files_cut}. answer = message content only, NEVER reasoning_content, passed through _clip.
5. One delegate at a time: a module-level lock; a second call while one runs returns {"error": "busy"} immediately.
6. Append one JSON line per call to /home/simon/jarvis-build/delegate-log.jsonl (time, first 200 chars of task, tokens, seconds, finish_reason).

Tests: after create_tool, delegate appears as one of your own tools (Open WebUI reads the tool list live). Call it as a tool; never read ~/.config/jarvis to curl it. Paste results:
- T1: task "What is 17*23? Answer with the number only." -> answer contains 391, no thinking text in answer.
- T2: files=[a small test file you create] and a question about its contents -> the answer uses them.
- T3: a task padded past 10000 tokens -> refused with the size error, no model call.
- T4: two calls at once -> exactly one "busy". If you cannot make two calls at once, quote the lock code instead and say T4 was not run.
- T5: after T1, check the llama-server log line for Simon's next chat turn (prompt eval tokens and ms) and record it in PROGRESS.md: this measures whether a delegate call pushes Simon's chat out of the shared cache (VERIFY item).

FOR SIMON: nothing to install (create_tool restarts the tool server by itself, about 3 s without tools). Tell him if T5 shows his next chat turn re-reading its whole history.
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
for f in 01-steps.md 07-builder-prompt.md 08-spec-delegate-tool.md; do echo "$f $(wc -l < $f) $(wc -c < $f) $(sha256sum $f | cut -c1-16)"; done; git -C ~/jarvis-build add handoff; git -C ~/jarvis-build commit -q -m "Handoff: Track J (builder preset, delegate tool)"; cd ~
