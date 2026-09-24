# jarvis-orchestrator

> Copied verbatim from Cowork (melange-wiki) on Sep 24 2026, with one redaction: the ntfy topic
> name is replaced by `<ntfy-topic>` (it lives on the box at `~/.ntfy-topic`).
> Cowork-only links kept as page names.
>
> Summary: The multi-slot model orchestrator/router Jack is building on jarvis-1 — slot inventory
> and status, verified router-model candidates, and the supervisor script design. Read before any
> orchestrator, router or model-slot work.

Hardware and engine constraints live in local-model-landscape (copied here as `v100-hardware-and-models.md`); build history in local-ai-setup; safety rules in jarvis-incidents.

## LIVE SURVEY Sep 14 2026 (run through Jarvis's own run_host_command in Open WebUI — all [MEASURED])

Services running: `agent-chrome` (headed Chrome + CDP), `agent-xvfb` (Xvfb :99), `agent-vnc` (VNC + noVNC on 127.0.0.1:6080), `browser-eval` (CDP-to-HTTP bridge), `browser-tools` (the port-8090 FastAPI tool server), `llama-server`. Two services here were not in prior notes: browser-eval and the xvfb/VNC pair, i.e. the agent Chrome is now HEADED on a virtual display with a watchable VNC view, not headless.

Ports listening: 3000 Open WebUI, 8080 llama-server (pid 27812), 8090 uvicorn browser tools (pid 1760), 8443 tailscale serve (on 100.87.7.19), 9222 Chrome CDP (127.0.0.1 only).

VRAM — THE BINDING CONSTRAINT, now measured: GPU0 15142/16384 MiB used, GPU1 14640/16384 used. ~1.2 GB free on card 0, ~1.7 GB on card 1. Persistence mode Enabled and power limit 200.00 W on BOTH cards, so the `nvidia-smi -pm 1` / `-pl 200` item recorded as "still open" in local-ai-setup IS DONE.

RAM: 251 total / 42 used / 209 available. Disk: /dev/nvme0n1p2 937G, 82G used, 809G avail (10%). HF cache holds only TWO repos: `ggml-org--Qwen3.8-27B-GGUF` 19G, and `unsloth--GLM-5.3-Flash-GGUF` at 12K — i.e. the stopped 31 GB GLM partial has been cleared, nothing to resume. llama.cpp: version 0.4.0-dev, build 10918, commit 82d6bb284, built with GNU 13.3.0.

~ contains: `agent/` (venv), `browser_eval.py` 4339 B, `browser_tools.py` 6437 B, `clean_tabs.py` 696 B, `jarvis-browse.py` 4517 B, `jarvis-memory/`, `memory_patch.py` 3639 B, `.chrome-agent/`. No supervisor file exists — jarvis-supervisor.py was never deployed. No router model downloaded.

## THE GPU-LAYOUT CONFLICT IS NOW RESOLVED, and the answer is CPU

With only ~1.2-1.7 GB free per card, a 1.28-1.31 GB Q4 router GGUF does NOT fit on either card alongside the 27B in any safe way. So the router runs CPU-only (`-ngl 0`), which is cheap: at the measured ~39 GB/s a 1.3 GB Q4 model reads 1.3 GB/token, and a routing answer is a handful of tokens, so a classification costs well under a second. This also removes the need for the supervisor's GPU1-swapping logic in v1 — there is no free card to swap into while the 27B is resident. Same reasoning applies to embedding/reranker/OCR/ASR: CPU, not GPU.

## SUPERVISOR DEPLOYED AND RUNNING — Sep 14 2026 [MEASURED]

`~/jarvis-supervisor.py`, 321 lines / 10,011 bytes, running under `~/agent/bin/python` (Python 3.12.3; fastapi, uvicorn, httpx all already present in that venv). Uvicorn bound to 127.0.0.1:8100. Verified live: `GET /health` → `{"ok":true,"managed_pids":{},"slots":{"judge":{"port":8080,"external":true,"healthy":true},"router":{...}}}`; `GET /v1/models` → `{"id":"jarvis","owned_by":"jarvis-supervisor"}`. Both 200 in the supervisor log.

HOW IT WAS TRANSFERRED (reuse this — it removes all transcription risk): Claude wrote the file locally, syntax-checked it, then POSTed the exact source to the browser-tool server's `/memory_write` endpoint (`https://jarvis-1.tail7b6a92.ts.net:8443/memory_write`, body `{name, content}`) from Jack's Chrome, landing it at `~/jarvis-memory/supervisor_src.md`. Jarvis then ran one short `cp` + `py_compile`. Byte count on the box matched the byte count sent exactly (10,011), so the model never retyped a line of it.

Structural safety properties actually in the code: no pkill/killall anywhere; `stop_slot` raises if the slot is marked external or its port == 8080; only PIDs recorded in `~/.jarvis-supervisor-state.json` are ever signalled; router or slot failure falls back to the judge; every response carries `_jarvis_route` {label, slot, port, reason}. NOT YET DONE: systemd unit (needs sudo — see below), so it does not survive reboot yet.

## NO PASSWORDLESS SUDO for the Jarvis shell tool [MEASURED Sep 14 2026]

Jarvis's `run_host_command` SSHes in as `simon` but has NO passwordless sudo, so anything needing root (installing a systemd unit, `systemctl enable`) must be pasted by Jack in a terminal. `sudo -n nvme smart-log` DID work, so some sudo paths are allowed; `systemctl` is not verified.

## `hf` CLI DOES NOT EXIST on jarvis-1 [MEASURED Sep 14 2026]

`~/agent/bin/python` has no `huggingface_hub`, and there is no `hf` on PATH — so the `hf download ...` commands in earlier notes CANNOT run as written. The working route is `llama-server -hf <repo>:<quant>`, which downloads into the HF cache itself (llama.cpp was built with libssl-dev so HTTPS works). Use that for every future model pull, or install huggingface_hub first.

## NEW: run_host_command — Jarvis has a full shell [MEASURED Sep 14 2026]

An Open WebUI Python tool named `run_host_command` SSHes from the Open WebUI container to `simon@host.docker.internal` using a key at `/app/backend/data/keys/jarvis-owui` and runs ANY command, timeout up to 600s, returning exit code plus last 20,000 chars. No allowlist, no denylist, no read-only mode. This is a major capability change from the era when Jarvis could only SUGGEST commands and Simon pasted them — the three pkill incidents in jarvis-incidents all happened under the old, SAFER arrangement. Jack's stated position Sep 14 2026 when this was flagged: he has a command he pastes that stops it, and considers that sufficient — he declined a tool-level denylist. Do not re-litigate; the guardrail therefore lives only in the system prompt.

Also new and not in earlier notes: the Jarvis model preset's toolIds had been reduced to `close_extra_tabs` only, and Open WebUI's `TOOL_SERVER_CONNECTIONS` was an EMPTY ARRAY — so Jarvis had lost its browser AND memory tools in chat even though `browser-tools.service` was running fine on 8090/8443. Claude re-registered the tool server and re-attached `run_host_command` to the preset Sep 14 2026 (both verified: "Model updated successfully", and "Browser - v1.0.0" now appears in the chat tool picker).

OPEN WEBUI GOTCHA CONFIRMED AGAIN (and AGAIN Sep 14 2026 in a fresh handoff chat — this keeps recurring, check it FIRST every new chat, before sending any task): Function Calling resets to "Default" on every NEW chat and must be set to Native in Controls → Advanced Params, or tools are described in prose and never called. Sep 14 2026 instance: a new handoff chat replied with "Explored 6 run_host_command, search_chats, view_chat" and appeared to report live-verified state, but Function Calling was still Default — so that report cannot be trusted as having run real commands, and the reply also drifted onto stale topics (GLM download, NVMe guard) pulled from old chat history via search_chats/view_chat rather than answering the actual handoff task. Caught by checking the Controls panel, fixed by clicking Function Calling → Native, then re-sent the task with an explicit warning to ignore the untrusted prior reply. Also: the plain `/api/chat/completions` REST endpoint returns `finish_reason: "tool_calls"` but does NOT execute the tool — execution only happens through the real chat UI's socket path. So tool-using work must be driven in the UI, not via the API.

## THE TARGET ARCHITECTURE, agreed Sep 14 2026 — "how do we make this a system and not a chat box"

DIAGNOSIS: today the MODEL IS THE SYSTEM. Everything lives in its context window, nothing happens unless Jack types, nothing outlives the conversation, and notifications do not exist. The fix is to demote the model to a component. This is the same principle already settled for the schoolwork tracker ("keep the model out of the retrieval path") generalised to everything.

FOUR LAYERS, and the model sits in 3-4 as a USER of the system:

1. State — one SQLite file, `~/jarvis.db`. Tables: `jobs`, `deadlines`, `findings`/`sources`, `runs`. Everything durable lives here, not in chat history. `runs` records wall-clock per job type so ETAs come from measured medians rather than guesses.
2. Workers — systemd services and timers that act on a schedule and write to the DB: a job worker (drains the queue, `type` field for coding vs research), a tracker (scrapes Cengage + D2L into `deadlines`), a notifier (reads DB, pushes ntfy).
3. Tools — the FastAPI server exposing the DB and queue to the model: `submit_job`, `check_jobs`, `whats_due`, `search`, plus the existing memory/browser tools.
4. Interfaces — the Open WebUI chat preset, a separate Open WebUI VOICE preset, and ntfy push to both iPhones.

BUILD ORDER, cheapest-to-systemness first: (1) SQLite + tool server, because without persistence nothing else matters; (2) job queue + worker, so work outlives the conversation; (3) ntfy, because the first unprompted phone buzz is the moment it stops being a chat box and Jack is motivated by visible wins; (4) scheduler, so things happen unasked; (5) then voice, harness, search.

FIRST MILESTONE that proves the whole spine in one loop: submit a job by chat or voice, walk away, get a phone notification when it finishes, come back later and ask "what happened" and it answers from the DB rather than from context. That single loop exercises queue, worker, state, notification, tool access and persistence. BLOCKER TO ASK JACK FOR: the ntfy topic name. It has been referenced in plans since Sep 7 but there is no `~/.ntfy-topic` on the box and no topic recorded anywhere in memory. (Resolved in layer 3 below.)

## OBSERVED BEHAVIOUR OF JARVIS, Sep 14 2026 — a full session of watching it work

Worth keeping because it changes where research effort should go. Its REASONING DISCIPLINE is already strong; its EVIDENCE SUPPLY is the bottleneck. What it did well, unprompted:

* Re-measured instead of trusting the prompt: "the 'no free VRAM' numbers I have on file (GPU0 15142/16384, GPU1 14640/16384) were measured 2026-09-14 and may be stale."
* Refused to report an unverifiable check as a pass: `sudo -n tmux ls` returned "a password is required", and it said "The guard line is a gap, not a pass" rather than assuming the SMART guard was running.
* Caught its own bad method and retested: its first backslash test used a BRE that means "literal backslash at end of line", it noticed, and re-ran with a fixed-string match.
* Noticed a contradiction in its own tool output: "diff_exit=0 with no diff lines means files identical, but the original has 19 literal $ and the new file has 0. Those two facts can't both be true."
* Caught a real bug in Claude's code before running it (the over-escaped `$` that would have made `kill \$(cat ...)` try to kill a process named `$`).
* Volunteered what it would NOT do (`echo 3 > /proc/sys/vm/drop_caches`, because it frees reclaimable page cache and buys zero headroom for a model load) and asked a question before executing.

THE ONE REAL FAILURE, and it is an epistemics failure not an arithmetic one: on the drive data it concluded "Drive is healthy... at this wear rate the drive has years of headroom; the spare pool is not the story on this drive." It computed 0.0838 %/GB correctly and then over-trusted it. `available_spare` only reports WHOLE PERCENTS, so any %/GB figure is a derivative of a staircase with 1-3 steps in the window. Claude made the same error the night before, in the opposite direction. Candidate rule for the operating manual: never state a rate derived from a coarsely quantised counter without saying how many steps it was computed from, and never let such a rate carry a verdict on its own.

THE STRUCTURAL GAP: every "research" move it made all session was reading LOCAL state. It never browsed, never cited an outside source, and its retrieval corpus is the ~15.6 KB identity pack. It has `open_page`/`read_page`, so it can READ a URL, but nothing observed gives it the ability to FIND one. Open WebUI's `web_search` capability is enabled on the preset but whether a search BACKEND is configured is UNVERIFIED — check `/api/v1/configs/...` or Admin Settings → Web Search when the box is up. If unconfigured, that capability flag is cosmetic and is probably the single cheapest research win available (self-hosted SearXNG, free, no API key). Foundation that is already unusually good: the browser stack is headed Chrome on Xvfb :99 with a VNC/noVNC view and a `browser-eval` CDP-to-HTTP bridge, so JS-heavy pages render properly. The weak link is finding pages, not reading them.

## SUPERSEDED SNAPSHOT — Sep 14 pre-reboot, condensed. Current truth is "POST-REBOOT GROUND TRUTH" below.

Still-useful details kept from it:

* Embedding server launch (verified working, CPU-only, GPUs untouched, on :8102): `llama-server -hf ggml-org/embeddinggemma-300M-GGUF --embedding -ngl 0 -c 2048 -b 2048 -ub 2048 -t 8` with `CUDA_VISIBLE_DEVICES=""`.
* Reranker still to download: `ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF`, 639,153,184 bytes, CPU.
* `~/jarvis-memory/glm_dl_script.md` = corrected GLM download script (2,162 bytes). Jarvis preset toolIds: `["close_extra_tabs","run_host_command"]`.
* Carried-forward open items: supervisor systemd unit; SMART watchdog `~/nvme-watch.sh` (spec written, never created); the RAG corpus, still unspecified and still blocking the anti-hallucination harness.

TWO ACCESS FACTS LEARNED THE HARD WAY Sep 14:

* `sudo -n tmux ls` returns "a password is required", so the root SMART guard tmux session CANNOT be verified from the `simon` account that run_host_command uses. Never report that guard as running; it is unverifiable, not confirmed.
* `sudo -n nvme smart-log /dev/nvme0` DOES work without a password. That is the permitted path for any drive tripwire, and is what a self-guarding script should use.

GOTCHA WORTH REUSING: writing a shell script through a JS template literal double-escaped every `$` into a literal `\$`, which `bash -n` PASSES but which is dead at runtime (`HOME_DIR="\$HOME"` sets a literal path, `kill \$(cat ...)` tries to kill a process named `$`). Jarvis caught it by reading the raw bytes with a fixed-string grep, not a BRE. Build such scripts as a JS ARRAY OF LINES joined with newlines, never a template literal. Also: replacing the source file between Jarvis's read and its copy made `diff` report "identical" while the byte counts disagreed; do not edit a staged file mid-flight.

## Sep 13 2026 model-selection research

Slot inventory, router model candidates, supervisor script design, GLM KV budget, retrieval-corpus inspection, and slot-by-slot picks (coding/embedding/reranker/OCR/ASR/TTS) — moved to jarvis-model-research to keep this file under the size cap. Read that file for model-selection/sizing questions.

## LAYER 1 BUILT AND VERIFIED — Sep 14 2026, via Claude-in-Chrome driving Jarvis (Jarvis did all the work via run_host_command)

`~/jarvis_db.py` (creates/migrates `~/jarvis.db`, WAL, foreign_keys=ON, 5 tables jobs/deadlines/findings/runs/approvals + 3 indexes, exactly per spec) and `~/jarvis_api.py` (single-file FastAPI, stdlib sqlite3, one conn/request, 13 endpoints: /health, /submit_job, /check_jobs, /job/{id}, /job/{id}/result, /job/{id}/claim, /whats_due, /deadline, /finding, /approvals, /approvals/{id}/decide, /eta) bound to 127.0.0.1:8110, running detached (setsid nohup, PID 9320 at build time, NOT yet a systemd unit — survives this session only). Log at `~/jarvis-api.log`. Full round-trip verified live: submit→claim (via `UPDATE...RETURNING`, SQLite 3.45.1)→result→/eta all returned correct JSON; deadline upsert dedupes on the UNIQUE key and preserves first_seen; approvals create/pending/decide all 200; claim-with-nothing-queued correctly 404s. Two spec deviations, both because the original approach lied or errored: `/claim` uses `UPDATE...RETURNING id` instead of SELECT-after-UPDATE (race/empty-result bug); deadline upsert does SELECT-then-INSERT/UPDATE instead of `ON CONFLICT...RETURNING` (SQLite's `changes()` misreported "inserted" on an actual update). Ports 8080/8100/8090/3000 untouched throughout; no pkill/killall used.

## LAYER 2 BUILT AND VERIFIED — Sep 14 2026, same session, health-checked first

Pre-build health check (all clean, stop-conditions defined in advance and none tripped): NVMe critical_warning 0, media_errors 0, available_spare 90% vs 10% threshold (dropped 93%→90% since the Sep 14 baseline on 8GB of writes — normal), percentage_used 0%, 21°C. Disk / 10% used, 803GB free. RAM 243/251GB available. Both GPUs idle 0%, 40/39°C, ~44W, VRAM 15046/14640 of 16384 MiB (judge model resident, matches baseline).

`~/jarvis_worker.py` (stdlib + httpx): loop claims via POST /job/{id}/claim (server picks oldest queued regardless of path id), sleeps 5s on 404/nothing-to-claim, runs the job (only `type=echo` implemented as a stub — echoes prompt back after 1s sleep, proves plumbing, real executors are a later layer), posts done+result or failed+error, whole cycle try/except-wrapped so one bad job can't kill the loop. Logs each cycle to `~/jarvis-worker.log`. Running detached (setsid nohup, stdin from /dev/null, PID 10097 at build time) — not a systemd unit yet, same as the API. Verified end-to-end: submitted echo job → claimed → completed in ~1s → visible via /check_jobs with correct result and timestamps.

Jarvis's own systemd recommendation: wait. Both files are still changing every layer (echo stub → real executors, worker will need concurrency/per-type config), and editing live units mid-development is where regressions creep in. Its suggestion: make them units after the notifications layer (layer 3), the last plumbing piece before the stack carries real load. Not acted on — needs Jack's confirmation.

## LAYER 3 BUILT AND VERIFIED — Sep 14 2026, same session. ntfy notifications, real phone push confirmed landing on ntfy.sh's own server.

Health-checked first each time (same 4 checks as layer 2, clean every time). ntfy topic: `<ntfy-topic>` (random, unguessable, ntfy.sh public instance, no account) — saved to `~/.ntfy-topic` chmod 600, single source of truth. Jack needs to subscribe to this topic in the ntfy app/web on his phone to actually receive the pushes — not yet confirmed done.

`~/jarvis_notifier.py` (stdlib+httpx, PID 12355 at last check): polls API every 15s, fires ntfy push on job done (priority 3, tag `job_done`+✅) / job failed (priority 5, tag `job_failed`+❌) / pending approval (priority 5, tag `approval_pending`+🔔, once each). Watermark persisted to `~/jarvis-notifier-state.json` (atomic tmp+rename, capped 2000 ids) so restarts don't miss or double-fire; fresh start seeds from history so old events never fire. Every poll cycle try/except-wrapped. Logs to `~/jarvis-notifier.log`. Verified end to end twice: submitted echo job → worker completed → notifier pushed → `curl https://ntfy.sh/<topic>/json` showed the actual message server-side (not just local log), with correct tags on the second proof. An earlier JSONL-only version (`~/jarvis_notify.py`) was built first (no channel had been specified yet) then superseded and stopped cleanly (PID 10725, verified via `ps -p` before kill). Test residue cleaned directly in SQLite (API has no DELETE endpoints) — jobs/approvals tables verified clean via curl afterward.

## SYSTEMD UNITS — written but NOT installed, Sep 14 2026

Three unit files written to `~/jarvis-memory/systemd/` on jarvis-1: `jarvis-api.service`, `jarvis-worker.service`, `jarvis-notify.service` (covers jarvis_notifier.py, the ntfy one). Pattern: `After=network.target`, `Restart=on-failure`, `RestartSec=3`, runs as `simon`, `ProtectSystem=full` + `ReadWritePaths=/home/simon`; worker/notify use `After=+Wants=jarvis-api.service` (not `Requires`, so api going down doesn't cascade-stop them — they retry on their own). Not installed: Jarvis has no passwordless sudo for systemctl, so Jack must paste the install/enable commands himself. Full unit file text was posted in chat but not yet pulled into memory verbatim — read the "Jarvis State Server" Open WebUI chat if the exact text is needed again, or ask Jarvis to re-paste from `~/jarvis-memory/systemd/`.

INSTALL COMMANDS, given by Jarvis Sep 14 2026 (not yet run — needs Jack's sudo, Jarvis cannot do this):

```
sudo cp ~/jarvis-memory/systemd/jarvis-api.service ~/jarvis-memory/systemd/jarvis-worker.service ~/jarvis-memory/systemd/jarvis-notify.service /etc/systemd/system/
sudo systemctl daemon-reload
kill 9320 10097 12355   # stop the loose nohup processes first (verify with ss -ltn|grep 8110 and ps -p before killing) — enable --now fails with "address already in use" otherwise
sudo systemctl enable --now jarvis-api.service
curl -s http://127.0.0.1:8110/health   # must return ok before starting the other two
sudo systemctl enable --now jarvis-worker.service
sudo systemctl enable --now jarvis-notify.service
```

Verify after: `systemctl status jarvis-api.service jarvis-worker.service jarvis-notify.service`; `curl -s http://127.0.0.1:8110/health`; submit a test echo job and confirm it completes via `/check_jobs`; `journalctl -u jarvis-worker -u jarvis-notify --since "2 min ago" --no-pager`. Final health check before session end, all clean: critical_warning 0, media_errors 0, available_spare 90% vs 10% threshold, / 10% used, 241GB RAM free, GPUs idle 37°C. Session ended cleanly Sep 14 2026 ~10:39am on Jarvis's own call ("stopping here, no changes made after this message") after finishing the requested report — good discipline, did not need a context-handoff note. Unit file full text was pasted in the "Jarvis State Server" Open WebUI chat and saved on-box at `~/jarvis-memory/systemd/*.service`; not duplicated into this memory file — read from the box when installing.

## SYSTEMD INSTALLED AND VERIFIED — Sep 14 2026, same day, Jack ran the commands himself

All three units enabled and confirmed running: `jarvis-api.service` (PID 14263, port 8110), `jarvis-worker.service` (PID 13584), `jarvis-notify.service` (PID 14009). No nohup processes left (old PIDs 9320/10097/12355 confirmed gone). Full loop re-proven under systemd: job 7 (echo/"systemd check") claimed by the systemd-managed worker, done in 1.03s.

REAL GOTCHA HIT AND DOCUMENTED, for reuse: Jack's install-order in the original commands put `kill 9320 10097 12355` AFTER `enable --now jarvis-api.service`, not before. Result: jarvis-api crash-looped 8 times (`NRestarts=8`, frozen not climbing — confirmed stable after) on "address already in use" while the old nohup api still held :8110; the first `curl /health` was answered by the dying nohup process, not the new unit. Correct order: kill the loose processes FIRST, verify `ss -ltn | grep 8110` is empty, THEN enable all three units. Also: Jack's pasted terminal output got cut off before the submit-job result, so Jarvis did not take the paste's apparent success at face value — it re-checked the DB directly (job was genuinely missing), diagnosed why from timestamps, and re-ran the proof itself rather than trusting the transcript. Worth citing as a model of the verification discipline this whole build has had. Session ended cleanly again on Jarvis's own call ("No changes made after this message. Good night.").

## LAYER 4 BUILT AND VERIFIED — Sep 14 2026, NEW CHAT (handoff-continued from the "Jarvis State Server" session above)

An uncommanded reboot happened between sessions, discovered by Jarvis unprompted: box shut down 04:17:58, back up 13:24 (clean systemd signal-15 sweep, not a crash). Casualty: the GLM-5.3-Flash download died mid-flight (4.6GB partial progress preserved in HF cache, resumable) and the standalone nvme-guard script died too — neither was a systemd unit yet. Deliberately NOT restarted this session (Jack said "pin it, not tonight"). All three systemd services (api/worker/notify) survived the reboot fine, confirming the Sep 14 systemd install actually works across reboots (first real-world proof, better than the planned-but-skipped deliberate reboot test).

GOTCHA HIT: a fresh Open WebUI chat defaults Function Calling to "Default" again, and this time it visibly produced an untrustworthy-looking first reply (drifted onto GLM/nvme-guard topics pulled from `search_chats`/`view_chat` instead of the actual handoff task) before being caught and fixed to Native. Once Native was set, Jarvis's subsequent replies were real, verified tool calls again. Lesson reinforced: check/set Function Calling to Native as the very first action in any new chat, before sending the real task.

`~/jarvis_healthcheck.py` (PID 20344 at build time): 60s poll, 6 checks — systemd status of api/worker/notify (worst-of: all down=down, partial=degraded), API /health, llama-server /health on :8080, NVMe SMART, disk free ≥40GB, RAM available ≥16GB. Alerts only on transition (→unhealthy prio 5 tag `health_down`, →ok prio 3 tag `health_up`), first cycle just baselines (no install-time spam), state in `~/jarvis-health-state.json` (atomic write) so restarts don't re-alert. Verification was genuinely rigorous: Jarvis tried a real `systemctl stop jarvis-worker` test first, discovered `sudo -n` covers nvme/smartctl/journalctl/dmesg but NOT systemctl for the simon account, so it fell back to injecting fake check results through the daemon's real `cycle()`+`push()`+state code path — then hit a real bug in its OWN test harness (a lambda closure capturing a stale dict), caught it, fixed it, and re-verified both the DOWN and RECOVERED pushes fired with real 200s from ntfy.sh. Honestly flagged the one thing it couldn't verify itself (a live systemctl-stop transition) rather than claiming full coverage.

Unit written, not installed: `~/jarvis-memory/systemd/jarvis-health.service` — deliberately does NOT `Wants=` the three services it watches (so it doesn't cascade-die with them, the whole point is alerting when they die). Install commands (same lesson as before — kill the loose process first):

```
kill 20344
ss -ltnp | grep 8110   # sanity check only, healthcheck holds no port
sudo cp ~/jarvis-memory/systemd/jarvis-health.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jarvis-health.service
systemctl status jarvis-health.service
tail -5 ~/jarvis-health.log
```

ntfy PUSH CONFIRMED WORKING END TO END — Sep 14 2026. Root cause of "no notifications" was simply that Jack had never subscribed to the topic on his phone (client-side, not a build bug). He installed the ntfy app, subscribed to `<ntfy-topic>`, and a fresh manual test push (HTTP 200, msg id NOHf7S2n1Lk5) landed. Notification pipeline (layers 3+4) is fully proven now, sender and receiver both confirmed.

## /stats ENDPOINT BUILT AND VERIFIED — Sep 14 2026, same session

Added to `~/jarvis_api.py` (line 285, backup taken first at `~/jarvis_api.py.bak-20260914164523`). Returns `queued_by_type`, `queued_total`, `running`, `failed_last_24h`, `durations_by_type` (median+samples per job type, same logic as /eta). Read-only. Jack had to do the systemctl restart himself (Jarvis's account has no sudo for systemctl, only for nvme/smartctl/journalctl/dmesg) — same pattern as every systemd change tonight. After restart (new PID 26435), Jarvis independently re-verified the whole chain rather than trusting the restart alone: /stats showed real data, submitted a fresh job which the systemd worker claimed within one cycle, the systemd notifier pushed it (confirmed via journalctl, since worker/notifier logs now go to the journal not their old files), and /stats read again showed the counter move. No false health alert during the restart blip, confirming the healthchecker's degraded-detection logic is sound in practice, not just in the injection test. Also noted: `~/jarvis-worker.log` / `~/jarvis-notifier.log` are now stale (systemd units log to journal instead) — use `journalctl -u <unit>` going forward; only the still-uninstalled healthchecker writes its own file.

STILL OPEN: (1) install jarvis-health.service (Jack, needs sudo — same one-liner as before); (2) decide the run_command executor type (deliberately deferred); (3) GLM download + nvme-guard restart (pinned); (4) worker concurrency/per-type executors, API auth; (5) housekeeping: clean stale log files, maybe a failed-job-count alert threshold. Coding harness (GVS5H-based) is the next big feature — see "CODING HARNESS" section below once built. Chats used: "Jarvis State Server" (layers 1-3 + systemd install) and a second same-named chat (layer 4, handoff-continued). Current live state: layers 1-4 all built and verified; 1-3 systemd-managed and reboot-tested for real; layer 4 written, tested, not yet installed. Drive/RAM/GPU health clean throughout every single check performed across both sessions.

## Still open

* The anti-hallucination RAG corpus is UNSPECIFIED and blocks the harness build. Jack's Sep 13 answer was "idk what its retrieving from, i think the knowledge I gave it" — i.e. he had not decided; the inspection above shows what is actually there. Jack was asked Sep 13 2026 to choose among: his own memory/notes files, course documents (PSEO syllabi/textbooks), live web research per query, or a combination. No answer recorded yet.
* GPU layout conflict: the 27B judge needs both V100s (16.5GB won't fit one 16GB card), which collides with GPU1 being the free worker slot for coding/vision/video. Unresolved; the supervisor's swapping logic assumes GPU1 is available, which it is not while the 27B is tensor-split.

## CODING HARNESS (GVS5H) — WIRED, AWAITING RESTART — Sep 14 2026 [MEASURED]

Health clean throughout (spare 90%, media_errors 0, critical_warning 0, ~802G free, 241G RAM, GPUs idle). [MEASURED] llama-server: n_slots=4, n_ctx_slot=133,376, generation rate 21.2 t/s (from print_timing). Cap chosen: 3 concurrent coding threads (slot 4 reserved for interactive chat). ESCALATION_CLOUD_MAX_TOKENS=16000 (Jarvis's own pick, reasoned: below the 40k threshold where the orchestrator's context-shrink retry fires, leaves ~117k of 133k slot ctx for prompt, 12.7-min worst case per call at measured rate). Job timeout 1800s (reasoning: trivial run ≈6 calls × 30-90s ≈3-8min, so 30min = 4x headroom).

Built: `~/jarvis_worker.py` rewritten (3 coding threads + 1 general thread + 1 reaper marking running>1960s as failed; claim now takes a `type` filter so coding threads only claim coding jobs) and new `~/jarvis_coding_run.py` (subprocess runner, imports vendored multiagent + CODE_SPEC, runs multiagent_solve in a thread, watchdog polls :8080/health every 15s, fails the job cleanly with "llama-server down mid-run, n_calls so far=N" if health fails for 60s straight instead of hanging forever).

TWO REAL BUGS Jarvis found and fixed in its own code before testing (exactly the "prove it, don't reason about it" catch):

1. Double-post: the coding runner posts its own job result, so `cycle()` was also posting `done` afterward on top of it, clobbering the real solution with "runner posted result." Fixed: cycle() now skips the post for coding jobs.
2. Real concurrency bug in `~/jarvis_api.py`: 8 parallel `/claim` calls returned 500s (SQLite objects across threads) and, under WAL, the claim's SELECT-then-UPDATE could theoretically double-claim a row. Fixed with `check_same_thread=False` + a process-wide non-reentrant `_WRITE_LOCK` around the entire claim transaction (acquired exactly once, no nesting/deadlock risk — verified).

Both files py_compile clean; type-filter claim tested working against the live (old) api pre-restart. First restart done, both tests attempted Sep 14 2026: 8-way concurrent no-double-claim test: PASSED [MEASURED] — exactly 5×200, 3×404, zero 500s, all 5 distinct job ids. Confirms the `_WRITE_LOCK` fix around the claim transaction holds under real concurrency.

Trivial coding job: root cause found and fixed [MEASURED]. Exact traceback: `PermissionError: [Errno 13] Permission denied: '/home/simon/jarvis_coding_run.py'` at `subprocess.py:1955 _execute_child`. Cause: the worker execs the runner relying on its `#!/usr/bin/env python3` shebang, but the file was never `chmod +x`'d (`-rw-rw-r--`, not a systemd sandboxing issue). Fixed two ways so neither assumption is load-bearing again: explicit interpreter in the worker's subprocess call (`/home/simon/agent/bin/python <runner>`) AND `chmod +x` applied.

Harness proven end-to-end standalone [MEASURED]: Jarvis ran `multiagent_solve` directly (bypassing the worker) with the real env — full plan+4 tasks+ideation(6 approaches)+worker-solve+primary pipeline completed in 126 seconds, output was a correct iterative Fibonacci (`a,b=0,1; for _ in range(n): a,b=b,a+b; return a`). This is the first full real run of the coding harness on jarvis-1, not just a connectivity check. Bonus proof: the reaper works [MEASURED]. It caught the orphaned `running` jobs from earlier testing (9, 14, 24) and the notifier correctly pushed all three as FAILED (priority 5) to ntfy — Jack will see 3 failed-job push notifications as test residue, not a real fault. Also reconfirmed in this same pass: 8-way no-double-claim still holds (5×200, 3×404, zero duplicates).

CODING HARNESS FULLY PROVEN END TO END — Sep 14 2026 [MEASURED]. Job 25 through the real worker: `status: done`, 27:05 wall, n_calls=7, finish_reason=stop, truncated_calls=0, infra_fail=None. Jarvis polled `:8110/job/25` by curl every 60s (not by watching in chat) until it flipped to done, then independently executed the returned fast-doubling Fibonacci and verified it: f(0)=0, f(1)=1, f(5)=5, f(50)=12586269025, f(1000)=209 digits, negative raises ValueError. Why 27min vs the 126s direct-bypass baseline — root cause, not a bug: harness has a 120s per-call timeout (`CLOUD_TIMEOUT`, orchestrator.py). Job 25 ran while a chat turn was generating on the same 27B, so llama-server cancelled and relaunched the task every ~110s with 7-8.7GB prompt-cache evictions; transcript shows worker:1 took 10 attempts, 9 discarded. Pure GPU contention. Rule: never benchmark a coding job while chat is generating — submit and poll by curl instead. Reaper, watchdog and result-posting all behaved correctly under real load.

## RELAY MODE CHANGED — Sep 14 2026: Claude no longer drives the browser

Jack switched to manual copy-paste: Claude writes the message, Jack pastes it into Open WebUI and pastes Jarvis's reply back. Reason: Claude-in-Chrome kept disconnecting mid-task, and completion-detection (the `find "stop generating button"` trick) was unreliable. Claude CANNOT reach jarvis-1 directly — verified by curl, the tailscale hostname is unresolvable from Claude's sandbox because it only exists on Jack's tailnet; Claude-in-Chrome only worked by riding Jack's browser's network access. Also reconfirmed: Open WebUI's `/api/chat/completions` REST endpoint returns `finish_reason: tool_calls` but never executes the tool, so there is no API shortcut either. If browser flakiness ever needs solving properly, the fix is exposing `jarvis_api.py` (:8110) through the same tailscale serve as browser-tools (:8443) so Claude could at least poll job state directly.

## TAILSCALE FUNNEL — WAS ON (public internet), CLOSED Sep 15 2026 ✅

RESOLVED. Fixed with `sudo tailscale funnel --https=443 off` (needs sudo; it deletes the handlers, so both were immediately re-added as tailnet-only with `sudo tailscale serve --bg --https=443 http://127.0.0.1:3000` and the same with `--set-path=/chat`). Verified: `tailscale serve status` now shows BOTH entries as `(tailnet only)` and no `# Funnel on:` block. Access from Jack's own devices unaffected. Watch for this returning — nothing is known to have turned it on in the first place.

The finding as originally discovered, kept because it explains the tool-server break below: `tailscale serve status` output, verbatim: `# Funnel on:` / `https://jarvis-1.tail7b6a92.ts.net (Funnel on)` with `/` and `/chat` both proxying to `http://127.0.0.1:3000` (Open WebUI). The `:8443` entry (browser-tools) is correctly marked `tailnet only` — only the root Open WebUI URL is funnelled. THIS CONTRADICTS A BELIEF RECORDED ACROSS SEVERAL MEMORY FILES that "everything today is private on Tailscale." It is not. Open WebUI, which hosts the Jarvis preset carrying `run_host_command` (unrestricted SSH to simon@jarvis-1), browser control and memory access, is reachable from the open internet. This is exactly the boundary jarvis-system-build WANT 7 calls non-negotiable: "a stranger must not be one prompt injection away from a shell on his server." What still protects it: Open WebUI's own login. So the security of the whole box rests on that auth being sound, the password being strong, signup being disabled or gated to pending-approval, and no auth-bypass CVE in v0.11.3. Also noted in the container log: `CORS_ALLOW_ORIGIN IS SET TO '*' - NOT RECOMMENDED FOR PRODUCTION DEPLOYMENTS`. Also corrects an earlier same-session conclusion: Claude's curl to that hostname failed from its sandbox and Claude concluded "unreachable because tailnet-only." The reason was wrong — the root URL is public; that curl failed for a proxy/TLS reason instead. Do not re-derive "it's private" from that failure.

## OPEN WEBUI RESTART Sep 15 2026 ~14:01 UTC — the "Unexpected end of JSON input" incident

Symptom Jack saw: two Jarvis replies in a row rendering only `Failed to execute 'json' on 'Response': Unexpected end of JSON input`. Cause: the Open WebUI container restarted mid-request (`Up 3 minutes`, log timestamps 14:01:24 vs server time 14:04:20), so the browser's in-flight request died with a partial/empty body. Not a Jarvis reasoning failure. NOT a crash: `RestartCount=0 ExitCode=0 OOMKilled=false Started=2026-09-15T14:01:05Z`. Docker's restart policy did not fire, so this was a clean start — host reboot or a manual/compose restart, not a container failure. Everything else measured clean at the time: disk 89G/937G (10%), RAM 237G available, no OOM kills in dmesg, llama-server active returning `{"status":"ok"}`, all three jarvis units active, API healthy with 23 jobs / 24 runs.

ROOT CAUSE, FULLY DIAGNOSED AND FIXED Sep 15 2026 — TWO separate bugs, both from the 14:01 container recreate.

BUG 1, the actual outage: WRONG PORT MAPPING. The recreated container had `-p 3000:3000`, but Open WebUI listens on 8080 inside (`PORT=8080`; `docker exec` proved `8080 -> 200`, `3000 -> FAIL`). Inspect showed `{"3000/tcp":[{"HostPort":"3000"}],"8080/tcp":null}` — host 3000 pointed at an empty container port while 8080 was unmapped. Symptoms that misled: `ss` showed 0.0.0.0:3000 LISTENING (docker-proxy binds it regardless) and docker reported the container healthy (its healthcheck probes 8080 from inside). Only `curl 127.0.0.1:3000` → `000` exposed it. Fix: recreate with `-p 3000:8080` → `port 3000: 200`.

BUG 2, the tool loss — NOT a startup race (Claude's earlier diagnosis here was WRONG and is corrected): the container genuinely cannot reach `https://jarvis-1.tail7b6a92.ts.net:8443`, on every restart, every time. Proof from inside the container: that URL fails `SSL: UNEXPECTED_EOF_WHILE_READING`, while `http://host.docker.internal:8090` and `http://172.17.0.1:8090` both return 200. The giveaway: `DNS jarvis-1.tail7b6a92.ts.net -> 209.177.145.97`, a PUBLIC address, not a 100.x tailnet one. The container doesn't use MagicDNS, so it resolves the name publicly — which only resolves at all because Funnel is on — then hits public ingress on 8443, where nothing is served publicly, so TLS dies mid-handshake. So Funnel being on is what broke Jarvis's tools.

FIX APPLIED Sep 15 2026: Claude changed the tool server URL in Admin → Settings → Integrations → External Tool Servers → Browser → Edit Connection, from `https://jarvis-1.tail7b6a92.ts.net:8443` to `http://host.docker.internal:8090`, via Claude-in-Chrome. Verified: `Initialized 1 tool server(s)` in 11 ms (previously 0 after a 2 s timeout). This should end the recurring tool loss permanently — it had been observed three times and was never random. NOTE on config precedence: the container env carries `TOOL_SERVER_CONNECTIONS=["http://host.docker.internal:8103"]` (a dead port — 8103 was the planned "big model" slot, nothing listens there), yet the app used the ts.net:8443 URL. Open WebUI's DB-stored config overrides the env var, so the env is only a first-run default. Change tool servers in the admin UI, not the env.

CULPRIT CONFIRMED: JARVIS. It gave Jack a `docker run` with `-p 3000:3000`, and did it TWICE in one day. Proven Sep 15 2026 when Jarvis handed Jack a second recreate block carrying the identical fingerprint — `-p 3000:3000` AND `--restart unless-stopped` — both differing from Jack's original in `~/.bash_history` (`-p 3000:8080 ... --restart always`). It took the whole interface down again. (Cron/timers were all ruled out first: no root crontab, nothing in /etc/cron.d or /etc/crontab, no systemd timer, and `clean_tabs.py` only closes Chrome tabs over CDP.) THE FAILURE MODE: Jarvis reads `3000/tcp` out of `docker inspect` and maps host 3000 → container 3000, not noticing the app listens on 8080 (`PORT=8080` is right there in the same env it read). It cannot see the consequence because recreating the container kills its own connection. This is a blind spot, not a one-off. Claude told Jack: do not paste docker commands from Jarvis without checking them first.

RELATED TRAP Claude hit: recreating the container DESTROYS manual in-container mutations. `run_host_command` needs `openssh-client`, which was `apt-get install`ed into the container filesystem (NOT the volume), plus the key at `/root/.ssh/id_ed25519` (`docker cp ~/.ssh/jarvis-owui`). Claude's own recreate silently wiped both and broke Jarvis's shell; Jarvis was rebuilding them when it reintroduced the port bug. Every recreate must re-run: `apt-get install -y openssh-client`, `mkdir -p /root/.ssh`, `docker cp ~/.ssh/jarvis-owui open-webui:/root/.ssh/id_ed25519`, `chmod 700 /root/.ssh && chmod 600 /root/.ssh/id_ed25519`.

FIX BUILT Sep 15 2026: `~/recreate-webui.sh` — canonical recreate script, correct `-p 3000:8080`, ssh/key re-provisioning included, self-verifying. Use it; never hand-write the docker run.

GUARDRAIL INSTALLED Sep 15 2026 — §14 "Docker and container operations" added to the Jarvis preset's SYSTEM PROMPT, not to ~/jarvis-memory, per the jarvis-incidents lesson that only the system prompt enforces every turn. Bans docker stop/rm/kill/restart against open-webui, bans hand-writing the docker run, points at `~/recreate-webui.sh`, explains the 3000-vs-8080 trap and the ssh/key loss. Verified server-side after save: 10,578 → 12,074 chars, 18 → 19 sections, §1 and §13 intact.

THE REAL LESSON, and it is Gap 1 from jarvis-system-gaps: Open WebUI was down ~20 min and nothing reported it — Jack discovered it via a broken-looking reply. `jarvis_healthcheck.py` watches llama-server, the job API and the three jarvis units, but NOT Open WebUI, the one piece he actually interacts with. Add a check on `http://127.0.0.1:3000/` expecting 200. ALSO LEARNED: simon is in the `docker` group (`988(docker)`), so Jarvis's `run_host_command` can stop/kill/recreate ANY container with no sudo and no password. §13 of the operating manual covers `kill`/`pkill`/`systemctl` but says nothing about docker — an uncovered destructive path, and the one container it could take down is the one Jarvis itself runs in. Worth adding to §13.

## POST-REBOOT GROUND TRUTH — Sep 14 2026 ~20:40 UTC [MEASURED by Jarvis]

* Supervisor: `~/jarvis-supervisor.py` on disk (10,011 bytes, matches the original transfer). Nothing on :8100, no `~/.jarvis-supervisor-state.json`. Died in the reboot, never a unit.
* :8102 embedding: dead, nothing listening. Also never a unit.
* HF cache: 27B 19G, Qwen3-1.7B (router) 1.2G, embeddinggemma-300M 319M, GLM partial 4.6G. No reranker downloaded.
* systemd units: exactly three — jarvis-api, jarvis-worker, jarvis-notify, all enabled+active. jarvis-health.service was NEVER installed; the healthchecker has been surviving as loose PID 20344 the whole time, and its `~/.jarvis-health-state.json` was lost in the reboot (re-baselines harmlessly).
* Core four healthy: :8110 ok, :8080 ok, worker active, notify active. (uvicorn on 8090/8091 is browser-tools, not ours.)

## ARCHITECTURE DECISION — small models are INDEPENDENT systemd units, supervisor is proxy-only. Sep 14 2026

Jarvis recommended it, Claude agreed and approved. Reasoning: (a) supervisor's own systemd restart would orphan child slots; (b) nothing restarts a crashed slot if the supervisor owns it, whereas independent units get `Restart=on-failure` free; (c) owning PIDs makes the supervisor a THIRD thing that can kill processes, which is the exact hazard class of the pkill incidents in jarvis-incidents; (d) the supervisor degrades to a dumb HTTP proxy + health aggregator, which is far easier to trust. Cost is that every slot start/stop becomes a paste for Jack, acceptable at 3 slots. The point that seals it: on-demand slot swapping existed to solve VRAM pressure, and that problem is gone — every small model runs CPU-only, and router 1.2G + embedding 319M + future reranker 639M ≈ 2.2GB against 232GB available RAM. Nothing to swap, so the supervisor loses nothing by giving up process management. Claude instructed that `start_slot`/`stop_slot`/managed-PID state/any signal-sending path be stripped from the code, not left dormant — if it cannot signal a process it cannot repeat the bug by construction.

## DRIVE FLAG — available_spare hit 90%, Sep 14 2026, and the monitoring gap it exposed

[MEASURED] NVMe: critical_warning 0, media_errors 0, err_log 0, percentage_used 0%, available_spare 90% vs threshold 10% — down from a 93% baseline over this session's writes. Jarvis flagged it unprompted as "check the drive tonight, not next week" and noted the old nvme-guard (which killed at <90%) is dead and acted on nothing. Jack has prior history here, see nvme-drive-failure. THE REAL GAP: the healthchecker's NVMe rule is an absolute floor only (`available_spare >= threshold+20`, i.e. 30%), so a 93→90 slide is completely invisible to it. Fix instructed: persist the last observed available_spare and alert on ANY decrease, plus any increase in media_errors/num_err_log_entries above zero, plus any nonzero critical_warning — keeping the absolute floor as well. Epistemics caution restated to Jarvis (both it and Claude have erred on this exact counter): available_spare reports whole percents only, so 93→90 is a three-step move on a staircase; any %/GB rate derived from it is imprecise. Report steps and window, never let a derived rate carry a verdict alone.

## OPEN DESIGN QUESTION put to Jarvis Sep 14 2026 — what does the router actually route TO?

There is effectively ONE model. Coding goes through GVS5H on the same 27B; vision is native to the 27B; GLM is pinned and not downloaded. So a router classifying which MODEL to use has exactly one answer and is pointless as built. Claude's proposal, pending Jarvis's assessment: route to PIPELINES, not models — straight chat to the 27B, a coding request submitted as a queue job and answered asynchronously, a factual question answered through retrieval with embedding+reranker in the path, a long research task queued as a background job. Same model underneath, different scaffolding, which is where the real quality difference lives. Specifically asked what the router should do when NOT confident, since misrouting a two-second chat question into a background job is a much worse failure than the reverse.
