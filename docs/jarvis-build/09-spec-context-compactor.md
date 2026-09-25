# J3 spec: context proxy (automatic, works even in the middle of a long turn)

Goal: Jarvis Builder never overflows and never needs Simon to start a new chat. A small proxy sits between Open WebUI and llama-server and sees EVERY model request, including each round of a tool loop, so it can act mid-turn (a filter only runs when Simon sends a message).

Build: ~/jarvis-build/ctxproxy/proxy.py (FastAPI + httpx in the venv), tests, a systemd unit file for Simon.
- Listens on 127.0.0.1:8113 for tests; the real unit binds 172.17.0.1:8090 so the Open WebUI container can reach it.
- Forwards everything to http://127.0.0.1:8080 unchanged (GET /v1/models, /health, etc.), including streaming (SSE) responses, chunk by chunk. Timeout 1800 s.
- For POST /v1/chat/completions it first counts the tokens of all message text via POST /tokenize (fallback len//3), then:
  - under warn (17000): forward untouched.
  - warn to compact (17000-19999): add one system message at the end: "CONTEXT HIGH (N/24576). Right now: update ~/jarvis-build/RESUME.md with the exact next action, commit, then end your turn with a 2-line status." Only once per conversation step (do not stack duplicates).
  - at or above compact (20000): compact what the model sees: keep the system message(s); add one system message "CONTEXT COMPACTED at N tokens. Earlier messages were removed from your view. Your handoff file says:" + the contents of ~/jarvis-build/RESUME.md (read directly from disk, max 6000 chars) + "Its age: M minutes. Continue from its exact next action; re-check facts with tools." Then keep the newest messages that fit in 8000 tokens, always including the last user message and never splitting an assistant tool_call from its tool result(s).
  - If RESUME.md is missing or older than 30 minutes: before compacting, make ONE extra request to llama-server (reasoning effort low, max_tokens 800) asking it to summarise the messages being removed into: goal, done, next action, open problems; use that as the handoff, labelled "auto-summary, may be incomplete".
- Every warn/compact writes one JSON line to ~/jarvis-build/ctxproxy/events.jsonl (time, tokens before/after, action).
- Fail open: any error in counting or compacting -> forward the original request untouched and log the error. The proxy must never be the reason a chat fails.

Tests (pytest, a fake upstream server on 127.0.0.1:8119 that records what it received; record and kill its PID):
- T1 small request -> forwarded byte-identical; streaming passes through.
- T2 18k tokens -> exactly one CONTEXT HIGH message added.
- T3 22k tokens with a fresh RESUME.md -> upstream receives system + COMPACTED(with RESUME text) + newest messages, under 12k tokens, last user message present.
- T4 cut would split a tool_call from its result -> both kept or both dropped.
- T5 RESUME.md missing -> auto-summary request made once, then compacted request.
- T6 /tokenize down -> estimate used; T7 a bug in compaction (force an exception) -> original forwarded.
- T8 GET /v1/models passes through.

FOR SIMON: install the unit (runs as simon, Restart=always); in Open WebUI add a second connection (Admin > Settings > Connections > OpenAI API > +, URL http://172.17.0.1:8090/v1, any key); point the Jarvis Builder preset's base model at the model from that connection. Plain Jarvis stays direct on 8080, so if the proxy ever breaks, normal Jarvis still works. Undo: point Builder back to the direct model, stop the unit.
