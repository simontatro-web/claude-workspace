# J3 spec: context compactor (upgrade the Context Watch filter)

Goal: the chat never overflows. When it gets long, the filter automatically replaces the old part of what the MODEL sees with a handoff, like starting a fresh chat, while Simon's screen keeps the full history. Open WebUI cannot open a new chat by itself, so this does the equivalent inside the same chat.

Two parts:
A) Jarvis keeps ~/jarvis-build/RESUME.md (max 40 lines): the same content as RESUME HERE (current step, done, exact next action, open problems, files touched, last commit). Update it whenever you update RESUME HERE. The filter reads THIS file, not PROGRESS.md.
B) Upgrade ~/jarvis-build/ctxfilter/context_watch.py (keep all existing behaviour and tests):
- New Valves: compact_tokens=19000, keep_last=6, resume_url="http://host.docker.internal:8200/read_file", resume_path="/home/simon/jarvis-build/RESUME.md", api_key="" (Simon fills this in Open WebUI; never hard-code it, never print it).
- In inlet, if count >= compact_tokens:
  1. Fetch RESUME.md via POST resume_url {"path": resume_path} with header Authorization: Bearer api_key (check the real read_file request/response shape in ~/jarvis-tools/main.py first; it may return only the last 4000 chars, which is why RESUME.md must stay small).
  2. New messages = [the original system message(s)] + [one system message: "CONTEXT COMPACTED at N tokens. Earlier turns were removed from your view. Your handoff file says:" + RESUME.md text + "Continue from its exact next action. Check facts with tools; do not trust memory of removed turns."] + the last keep_last messages. Never cut a tool call away from its tool result: if the cut lands between them, keep both.
  3. If the fetch fails: do not compact; append the CONTEXT CRITICAL warning instead (old behaviour). Never raise.
- Below compact_tokens, the existing NEARLY FULL / CRITICAL warnings stay as they are, and they now also say "update RESUME.md".

Tests (venv python, fake bodies; start a tiny local HTTP server on 127.0.0.1:8119 that mimics read_file for the test; record and kill its PID):
- T1-T5: the existing tests still pass.
- T6: a 20k-token body -> compacted: system prompt kept, one COMPACTED message containing the fake RESUME text, exactly the last 6 messages kept, total under 8k tokens.
- T7: the fetch server is down -> no compaction, CRITICAL warning appended, no exception.
- T8: the last-6 cut would split a tool call from its result -> both kept.

FOR SIMON: re-paste the filter in Open WebUI (Admin > Functions > Context Watch > edit), then set its valve api_key to the tool server key (the same Bearer key Open WebUI already uses for the tool server). Test: a long chat past ~19k tokens keeps working and Jarvis continues from RESUME.md.

Known limit (VERIFY): Open WebUI may run filters only when Simon sends a message, not between Jarvis's own tool calls. The turn budget in the builder prompt is still needed.
