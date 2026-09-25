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
- docs/jarvis-build/ctxproxy/: the J3 context proxy, BUILT BY CLAUDE and tested off-box:
  proxy.py, tests/ (51 tests, fake llama-server), smoke_real.py (real-server checks), report.py (events
  summary, suggests RESERVE), live/setup_task.py + check_task.py (25-edit acceptance task and grader),
  ctxproxy.service, README.md (the install and acceptance runbook; read it first).
- docs/jarvis-build/ctxproxy-bundle.tgz: what Simon installs; sha256
  4758c4fbc17ec6e6636b3ddda62103f6af9b6e65512272c49208831065fd1628. If you change any ctxproxy file,
  rebuild it the same way (tar --sort=name --mtime='2026-09-25 00:00Z' --owner=0 --group=0 --numeric-owner,
  containing ctxproxy/ and handoff/01-steps.md + handoff/09-spec-context-compactor.md), re-run the tests from
  a clean extract, and give Simon the new checksum.

## Proxy design in one paragraph (details in proxy.py and README.md)
Open WebUI -> 172.17.0.1:8090 -> 127.0.0.1:8080. Counts messages + tools via /tokenize (cached; len//3 fallback).
warn_at 14576: appends a CONTEXT HIGH note to the last user/tool message. compact_at 17576 (= 24576 - RESERVE 6000
- 1000): keeps system + a frozen CONTEXT COMPACTED note (RESUME HERE block of PROGRESS.md, or auto-summary if
missing/older than 30 min) appended to the first system message + pinned last user message + newest whole
units; result ~11-12k. Sticky: state keyed by a hash chain over non-system messages, so later requests
(Open WebUI resends full history) get the identical prefix; state.json survives restarts. Messages over 4000
tokens are cut head 2500 + tail 1000. "### Task:" and X-Ctxproxy-Skip requests pass untouched. Fail-open, but
a request over limit - 1024 gets a clear 400. events.jsonl: numbers only, rotates at 5 MB.

## Where things stand (end of the last session)
Simon has NOT installed the proxy yet. His next steps (README 1-4): scp + checksum + extract + pip install,
`venv/bin/python -m pytest -q ctxproxy/tests` (expect 51 passed), `venv/bin/python ctxproxy/smoke_real.py`
(expect 6/6). He will paste you the output. The two smoke checks that matter most: C3 (our count within 5% of
llama-server's) and M1 (cache reused after compaction). If C3 under-counts, raise CTXPROXY_OVERHEAD_PCT or
PER_MSG_TOKENS; if the template rejects the compacted request, change where notes go.
Checked again 2026-09-25 (MEASURED, Claude's sandbox): the checksum above matches, and a clean extract passes
51/51 on Python 3.11.15 and 3.12.3. Known gap, fix on the next bundle rebuild: smoke_real.py waits forever if
127.0.0.1:8113 is already taken (uvicorn's bind error ends its thread; the start loop has no timeout). Until
then Simon runs a port check first. Run pytest with `-p no:cacheprovider` so ~/jarvis-build gets no
.pytest_cache. Gate 5 cannot pass before J2b: the 8000 cap makes the xhigh delegate call return nothing.

## Queue, in order
Proposed 2026-09-25 and waiting for Simon's OK: MASTER-PLAN.md Stage A reorders items 1-5 below (B1 backup
alongside the acceptance runs; Builder prompt v2 before them; J2b before gate 5; one regression run at the end).
Once Simon confirms, follow Stage A there.
1. Help Simon through ctxproxy README 1-4; fix anything the real server shows; rebuild the bundle if needed.
2. README 5-6: service install (env file with client key; check container reach to 172.17.0.1:8090),
   Open WebUI connection, Builder base model -> proxy, Task Model -> direct, context_watch filter OFF on Builder.
3. README 7 acceptance: 3 PASS runs of the 25-edit task each with >=1 compaction (one with >=2), one
   interrupted-and-resumed run, gate 5 (P4b: delegate at xhigh while the chat is past ~15k). Read every
   check_task.py and report.py output; set CTXPROXY_RESERVE from report.py. Until all gates pass, the manual
   new-chat routine (RESUME HERE) stays the official method.
4. J2b delegate fix-up (spec: docs/jarvis-build/08-spec-delegate-tool.md, J2b section). Known: the plugin in
   ~/jarvis-tools/plugins has `_MAX_OUTPUT_TOKENS = 8000` at line 16, which made two xhigh calls return nothing;
   needs: cap 16000, explicit error on finish_reason "length" with empty answer, expanduser on paths, log to
   ~/jarvis-build/logs/ with metadata only, X-Ctxproxy-Skip header, move test leftovers
   (delegate-log.jsonl, delegate-oversized.txt, delegate-test-file.txt in ~/jarvis-build root). You need the
   plugin source first: ask Simon for `cat ~/jarvis-tools/plugins/*delegate*` and one other plugin (e.g.
   gpu_status) to copy the exact plugin pattern (decorator, auth dependency, pre-injected names). Either you
   write it and Jarvis installs it via create_tool, or Jarvis does it from the spec; ask Simon which.
5. J4 replace_in_file tool (spec 10-spec-edit-tool.md); then Simon adds the one rule line to the Builder prompt.
6. Then Jarvis continues 01-steps.md: B1 backup to the USB drive (needs from Simon:
   `findmnt /mnt/models -o SOURCE,FSTYPE,OPTIONS; sudo docker inspect open-webui --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'`),
   S2 watchdog, S3 job DB with the spec gate, S4 worker. Then the roadmap phases.
Also pending: the reasoning-effort three-mode test (expected answer 62), optional purge of lxd-installer,
storing the restic password off the box.

## Lessons (read these)
- Jarvis has claimed changes he did not make. Always check with `git -C ~/jarvis-build show --stat HEAD` and
  `git status --short`; ask for real output, never accept a summary.
- Jarvis's context is 24,576 tokens including his xhigh thinking; long prompts, big tool outputs and shell
  quoting puzzles fill it. Give him small steps, a tool-call budget per turn, and a 2-line status when out.
- A pasted prompt once still contained "[PASTE THE OUTPUT HERE]"; check prompts for placeholders.
- Don't `rm -rf` a variable path in your own sandbox; the safety check blocks it. Use fresh mktemp dirs.
