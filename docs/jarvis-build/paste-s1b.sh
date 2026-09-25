cd ~/jarvis-build/handoff
cat >> 00-START-HERE.md <<'JBH_END'

## Checkpoint rule (added by Simon; read this first)
Your context is only 24,576 tokens and you cannot see how full it is.
- Keep a block at the TOP of ~/jarvis-build/PROGRESS.md titled "RESUME HERE" (max 15 lines): current step, what is done, the exact next action, open problems, files touched.
- Rewrite it after EVERY finished sub-task (a test passing, a commit), not only at the end.
- If a system message says CONTEXT NEARLY FULL or CONTEXT CRITICAL: update RESUME HERE, commit, tell Simon to start a new chat, and stop.
- A new chat reads RESUME HERE first and continues from its "exact next action".
JBH_END
cat > 05-spec-context-filter.md <<'JBH_END'
# S1b spec: context-watch filter (Open WebUI Filter function)

Why: the chat window is 24,576 tokens and you cannot see how full it is. When it overflows, history is cut silently. This filter measures the chat before every turn and warns you in time.

File: ~/jarvis-build/ctxfilter/context_watch.py, one Open WebUI Filter function (Simon pastes it into Admin > Functions; you never touch Open WebUI).

Shape (standard Open WebUI filter):
- class Filter with class Valves(BaseModel): warn_tokens=17000, hard_tokens=21000, tokenize_url="http://host.docker.internal:8080/tokenize", timeout_s=3.
- def inlet(self, body: dict, __user__: dict = None) -> dict
  1. Join the text of every message in body["messages"] (content as string; if content is a list, join its "text" parts; include tool-result messages).
  2. POST {"content": joined} to tokenize_url, count = len(response["tokens"]). If the call fails, fall back to len(joined) // 3 and mark it "estimated".
  3. If count >= warn_tokens: append a system message: "CONTEXT NEARLY FULL (N of 24576 tokens). Before anything else: update the RESUME HERE block in ~/jarvis-build/PROGRESS.md, commit, then tell Simon to start a new chat. Do not start new work."
  4. If count >= hard_tokens: same message but "CONTEXT CRITICAL" and "do only the checkpoint".
  5. Never raise: wrap everything in try/except and return body unchanged on any error.
- No outlet needed.

Tests (run with the venv's python, no Open WebUI needed; paste output):
- T1: a fake body with 3 short messages -> body unchanged.
- T2: a fake body whose text tokenizes to ~18,000 tokens (repeat a paragraph) -> exactly one CONTEXT NEARLY FULL system message appended. Use http://127.0.0.1:8080/tokenize for the test (you are on the host).
- T3: tokenize_url pointed at a closed port -> falls back to the estimate, still warns on a long body, no exception.
- T4: content given as a list of {"type":"text","text":...} parts -> counted correctly.

FOR SIMON: how to add it in Open WebUI (Admin Panel > Functions > + > paste > Save > enable, then attach it to the Jarvis model or make it global) and a test: start a chat, paste a long document, and check the warning appears.
JBH_END
sed -i 's/^| S2 |/| S1b | Context-watch filter for Open WebUI (warns before the context overflows) | 05-spec-context-filter.md | Simon pastes it into Open WebUI |\n| S2 |/' 01-steps.md
for f in 00-START-HERE.md 01-steps.md 05-spec-context-filter.md; do echo "$f $(wc -l < $f) $(wc -c < $f) $(sha256sum $f | cut -c1-16)"; done; cd ~
