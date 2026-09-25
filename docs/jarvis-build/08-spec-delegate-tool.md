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
