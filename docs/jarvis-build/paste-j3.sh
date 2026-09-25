cd ~/jarvis-build/handoff
cat > 09-spec-context-compactor.md <<'JBH_END'
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
| J3 | Context compactor: auto-handoff when the chat gets long | 09-spec-context-compactor.md | Jarvis builds; Simon re-pastes the filter |
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
for f in 01-steps.md 09-spec-context-compactor.md; do echo "$f $(wc -l < $f) $(wc -c < $f) $(sha256sum $f | cut -c1-16)"; done; git -C ~/jarvis-build add handoff; git -C ~/jarvis-build commit -q -m "Handoff: J3 context compactor spec"; cd ~
