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
