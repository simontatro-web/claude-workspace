# Handoff for the next Claude session (written 2026-09-25, Chicago)

You are continuing work for Simon on "Jarvis", his local AI on his server jarvis-1. Your job: build, tweak and
improve Jarvis so he can effectively and accurately build out Simon's orchestrator plan. You may build code
yourself in this repo; Simon runs everything on the box and pastes you the output.

## Rules from Simon (do not break)
- Call him Simon. Never use the name "Jack". Times in Chicago time.
- Label factual claims about the box: MEASURED (Simon pasted output), SOURCE (docs), ESTIMATE, VERIFY (unchecked).
- You cannot reach jarvis-1. Never claim something ran there unless Simon pasted the output.
- Every command you give Simon: small paste blocks (a ~200-line paste broke his terminal once; keep blocks under
  ~60 lines), read-only where possible, and for anything that changes the box: what it changes, a test, an undo.
- Bigger files go to the box as a tar bundle: Simon downloads it raw from GitHub on his Windows PC and runs
  `scp $HOME\Downloads\<file> simon@jarvis-2:~/`, then checks `sha256sum` against the value you give him.
- Never do Simon's graded schoolwork.
- No model identifiers (names or ids of AI models) in commits, files or PRs.
- Work and push only on branch `claude/orchestrator-research`. Never push to `claude/new-session-uyo1y3`.
  Do not edit docs/HANDOFF.md, docs/bench/, docs/benchmarks/.
- If Simon gives a startup/business idea, never weight his past ideas.
- Simon runs one Jarvis chat at a time (the server is set up for speed).

## The box (MEASURED unless marked)
- jarvis-1 (tailnet name jarvis-2): 2x Xeon E5-2699 v3, 503 GiB RAM, 2x V100-16GB.
- Jarvis = a 27B Q4_K_M model on llama-server 127.0.0.1:8080: -c 24576, --parallel 2, --kv-unified,
  reasoning effort xhigh, MTP draft. /props and both /slots report n_ctx 24576. Whether the two slots share ONE
  24576 pool is VERIFY (gate 5 / P4b tests it). Per-request `chat_template_kwargs` {"enable_thinking": false}
  or {"reasoning_effort": low|medium|xhigh} works.
- Open WebUI on port 3000 (docker container `open-webui`). Tool server on port 8200 runs as simon; plugins in
  ~/jarvis-tools/plugins, added by Jarvis via create_tool. Presets: plain "Jarvis" and "Jarvis Builder"
  (system prompt = docs/jarvis-build/07-builder-prompt.md; Simon must still add its turn-budget line).
- Open WebUI filter `context_watch` (S1b) is installed; it warns CONTEXT NEARLY FULL / CRITICAL.
- ~/jarvis-build is a git repo (branch master): handoff/ (copies of docs/jarvis-build/*.md), PROGRESS.md with a
  "RESUME HERE" block at the top, backup/ (S1, restic, tested locally), ctxfilter/, delegate test leftovers,
  ctxproxy/STRESS-PLAN.md (written by Jarvis: 57 rows + ACCEPTANCE gates; a v2 revision chat may have run).

## What exists in this repo
- docs/jarvis-build/MASTER-PLAN.md: READ THIS SECOND. Every want mapped to a step, stages A-H with gates, the
  definition of DONE, the per-step loop, open decisions, and a status log. Keep its Status column and log current,
  and only from output Simon pasted.
- docs/orchestrator-research.md, docs/orchestrator-roadmap.md: the full plan (24 Part-4 wants + 15 new wants
  in docs/orchestrator-wants-simon-2026-09-25.md), decisions D1-D23, buy list. The roadmap may have been edited
  by something else; the file on disk is current.
- docs/jarvis-build/: the build handoff Jarvis reads (00-START-HERE, 01-steps, specs 02-10).
- docs/jarvis-build/ctxproxy/: the J3 context proxy v2.1, BUILT BY CLAUDE and tested off-box:
  proxy.py, tests/ (64 tests, fake llama-server), smoke_real.py (8 real-server checks), report.py (events
  summary, suggests RESERVE), live/setup_task.py + check_task.py (25-edit acceptance task and grader),
  ctxproxy.service, README.md (the install and acceptance runbook; read it first).
- docs/jarvis-build/autopilot/: BUILT BY CLAUDE. autopilot.py runs one approved task with nobody typing
  "continue" (through the proxy, tools via the tool server's OpenAPI, seatbelt, limits, PAUSE, fresh chat for
  the same run when a chat gets too long, DONE checked with git + --verify, transcript/events/summary in
  runs/<id>/, optional ntfy). jarvis-autopilot = the root-owned command Simon installs in /usr/local/bin.
  tasks/ (acceptance, next-step, seatbelt-test), tests/ (131 tests: scripted fake model, fake OpenAPI tool
  server running real commands in a temp git repo, one test through the real proxy, CLI SIGTERM/lock, wrapper
  dry-run). README.md is its runbook (install, key, check, gates AP-1..AP-4, real work).
- docs/jarvis-build/07-builder-prompt.md is Builder prompt v2 (STATUS: DONE/BLOCKED lines, no turn budget,
  NEW CHAT START / CONTEXT HIGH / CONTEXT COMPACTED rules, AUTOPILOT meaning). The autopilot reads it from
  ~/jarvis-build/handoff/07-builder-prompt.md, so the chat preset and the autopilot share one prompt.
- docs/jarvis-build/jarvis-build-bundle.tgz: the current bundle, sha256
  0402e2701496ca565ef09a61d62b18d8243c7a28df754912ee65d2dacd3b7ef1 (195 tests: adds resumes.json to
  ctxproxy/.gitignore and drops the schoolwork line from handoff/07). Simon installed the previous one,
  80ee0c6f, and applied those two changes on the box by hand (sed + one .gitignore line). Contains ctxproxy/, autopilot/,
  handoff/00-START-HERE.md, 01-steps.md, 07-builder-prompt.md, 09-spec-context-compactor.md. Rebuild it the
  same way (staging dir, no __pycache__, files 644 except autopilot/jarvis-autopilot 755, tar --sort=name
  --mtime='2026-09-25 00:00Z' --owner=0 --group=0 --numeric-owner), re-run both suites from a clean extract,
  and give Simon the new checksum.

## Proxy design in one paragraph (details in proxy.py and README.md)
Open WebUI -> 172.17.0.1:8090 -> 127.0.0.1:8080. Counts messages + tools via /tokenize (cached; len//3 fallback).
First request of a new chat (one non-system message): appends a NEW CHAT START note (RESUME HERE block + `git log
--oneline -5` + `git status --short` of CTXPROXY_GIT_DIR, default ~/jarvis-build) to the first system message,
frozen per chat in resumes.json (keyed by chain[2] once the chat has a reply, else chain[1]); header
X-Ctxproxy-No-Resume or CTXPROXY_RESUME_NEW_CHATS=0 turns it off; a chat that started before the proxy gets none.
warn_at 14576: appends a CONTEXT HIGH note to the last user/tool message. compact_at 17576 (= 24576 - RESERVE 6000
- 1000): keeps system + a frozen CONTEXT COMPACTED note (RESUME HERE block of PROGRESS.md, or auto-summary if
missing/older than 30 min, plus the git facts) appended to the first system message (it replaces the NEW CHAT
START note) + pinned last user message + newest whole units; result ~11-12k. Sticky: state keyed by a hash
chain over non-system messages, so later requests (Open WebUI resends full history) get the identical prefix;
state.json survives restarts. Messages over 4000 tokens are cut head 2500 + tail 1000. "### Task:" and
X-Ctxproxy-Skip requests pass untouched. Fail-open, but a request over limit - 1024 gets a clear 400 (the
autopilot answers that with a fresh chat for the same run). events.jsonl: numbers only, rotates at 5 MB.

## Latest (read first): A1 is DONE on the box (MEASURED; see MASTER-PLAN status log). 194 passed, smoke 8/8.
Next: ctxproxy/README.md step 5 (service), step 6 (Open WebUI + Builder prompt v2), then autopilot/README.md.
Before the first `jarvis-autopilot next-step`: clear the 4 untracked leftovers in ~/jarvis-build (log lists them).
Simon's choice (2026-09-25): the line "Never do Simon's graded schoolwork." is removed from the Builder prompt
(07-builder-prompt.md; Open WebUI's live Builder prompt already lacks it). jarvis-build-bundle.tgz (80ee0c6f, the
installed one) still had it; the current bundle 0402e270 does not. 00-START-HERE.md keeps the line (Simon: no).

## Where things stand (end of the last session, 2026-09-25 evening Chicago)
Simon asked for Jarvis to continue automatically with no "continue" from him; he is away from his computer and
told Claude to keep working so it is ready when he is back. Built and pushed: proxy v2.1, the autopilot,
Builder prompt v2, 00/01/09 updates, MASTER-PLAN Stage A rewritten around them (A1-A10). NOTHING of this is on
the box yet. His next steps: ctxproxy/README.md 1-4 with jarvis-build-bundle.tgz (expect `194 passed`, smoke
`8/8 passed`), then README 5-6 (paste Builder prompt v2), then autopilot/README.md 1-5.
Checked (MEASURED, Claude's sandbox): a simulated box (fresh git repo with old handoff files, fresh venv, latest
starlette/uvicorn/httpx/pytest) extracts the bundle, passes 194/194 on Python 3.12.3 and 3.11.15, and the gated
commit (`grep -q "^194 passed"`) leaves `git status` empty. smoke_real.py now exits 2 with a clear message if
127.0.0.1:8113 is taken; against a fake server it runs all 8 checks (3 fail there by design: no cache, fake
counts). Run pytest with `-p no:cacheprovider` so ~/jarvis-build gets no .pytest_cache.
Smoke checks that matter most: C3 (count within 5%), M1 (cache reused after compaction), R2 (new-chat note
reused). If C3 under-counts, raise CTXPROXY_OVERHEAD_PCT or PER_MSG_TOKENS.
VERIFY on the box (the tests cannot): the tool server's auth scheme and key location (autopilot README step 2
asks Simon for `systemctl cat jarvis-run-host-commands`, key redacted); the real operationIds; that llama-server
streams tool calls in the OpenAI delta format (`jarvis-autopilot check` probes it); how Open WebUI ends long
tool loops. Gate 5 cannot pass before J2b: the 8000 cap makes the xhigh delegate call return nothing.
Commits: earlier commits on this branch carry a co-author line naming the model (against Simon's rule); Claude
told Simon and left history alone. New commits carry only the Claude-Session line.

## Queue, in order
Follow MASTER-PLAN.md Stage A (A1-A10), then stages B-H. Details per step:
- A1-A3: help Simon through ctxproxy/README.md 1-6 and autopilot/README.md 1-3; read every output; fix and
  rebuild the bundle if the real server disagrees.
- A4: autopilot gates AP-1..AP-4 + one Open WebUI chat run + gate 3; read every `jarvis-autopilot status`,
  check_task.py and report.py output; set CTXPROXY_RESERVE from report.py. Until all pass, the manual new-chat
  routine (RESUME HERE) stays the official fallback.
- A5 B1 backup: needs from Simon `cat` of ~/jarvis-build/backup/{jarvis-backup.sh,sqlite_snap.py,config.env},
  `findmnt /mnt/models -o SOURCE,FSTYPE,OPTIONS` and
  `sudo docker inspect open-webui --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'`.
  Install a root-owned copy (/usr/local/sbin + /etc/jarvis-backup/, config mode 600), never the file in
  ~/jarvis-build (S1 review finding). Plus the fstab line for the drive (ro, nofail, by UUID, ntfs3).
- A6 J2b (spec 08, J2b section): `jarvis-autopilot next-step --allow-create-tool`. Known: the plugin has
  `_MAX_OUTPUT_TOKENS = 8000` at line 16. Ask Simon for `cat ~/jarvis-tools/plugins/*delegate*` and one other
  plugin first, so you can review Jarvis's diff against the exact plugin pattern.
- A7 gate 5 / J2c; A8 J4 (spec 10) by autopilot, then the rule line in the Builder prompt; A9 regression run.
- A10 loose ends: reasoning-effort three-mode test (expected answer 62), optional purge of lxd-installer,
  restic password off the box, W22 writing folder.
- Then Stage B: S2 watchdog, S3 job DB with the spec gate, S4 worker, each as `jarvis-autopilot next-step`
  (Simon at home), then Claude reviews the foundation. Runs while Simon is away: only after R1.5 and R1.6.

## Lessons (read these)
- Jarvis has claimed changes he did not make. Always check with `git -C ~/jarvis-build show --stat HEAD` and
  `git status --short`; ask for real output, never accept a summary.
- Jarvis's context is 24,576 tokens including his xhigh thinking; long prompts, big tool outputs and shell
  quoting puzzles fill it. The proxy and the autopilot now carry him across compactions and chats, but only
  what he wrote into RESUME HERE and git survives: keep specs small and insist on commits after each sub-task.
- A pasted prompt once still contained "[PASTE THE OUTPUT HERE]"; check prompts for placeholders.
- Don't `rm -rf` a variable path in your own sandbox; the safety check blocks it. Use fresh mktemp dirs.
