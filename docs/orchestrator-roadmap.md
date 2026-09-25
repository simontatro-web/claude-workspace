# Jarvis orchestrator roadmap (2026-09-25)

For Simon. This is the ordered build plan for `docs/orchestrator-research.md`: every section number, N-want, W-want and decision D# below points there.

**Rules for every step**
- **Small:** one evening or less.
- **Testable:** a pass/fail test written before building.
- **Reversible:** the undo is stated.
- **Downtime stated.**
- **Nothing here is a command.** When a step starts, Claude writes the exact files and commands for that step, with checksums, and you run them. Root-level steps are always yours. Jarvis may write code only in its own sandbox once the fences exist.
- **Production stays untouched:** the 27B unit and Open WebUI are never edited without a backup and a test on a spare port (HANDOFF rules).
- **The benchmark campaign keeps priority on Jarvis-off windows (D18).** Steps marked "no downtime" can run any time.

Labels as in the research doc. Effort per step: ESTIMATE.

---

## Phase 0: settle facts and decisions (read-only, no downtime)

**0.1 Run the read-only checks V1-V22** (research doc section 7) and paste the output.
- Pass when every VERIFY that the Phase 1 steps depend on has an answer: V1-V5, V12-V15.

**0.2 Decide D1-D5** (fence, network, backup target, driver hold, HF token).
- Phase 1 cannot finish without D1 and D3.

**0.3 Start writing capture now (W22).**
- A plain folder plus a note in your routine. No code, no risk, and it gates the style fine-tune later.

---

## Phase 1: safety foundations (before any unattended or self-modifying work)

### 1.1 Off-box backup (W19, your #1 on paper). No downtime.
- **Build**
  - restic repository on Backblaze B2 (D3).
  - Nightly systemd timer.
  - SQLite files copied with the SQLite backup API (`.backup` / `VACUUM INTO`), never `cp` of a live file. That includes Open WebUI's database, read through the container's Python, since the container has no sqlite3 (jarvis-run-host-commands).
- **Includes**
  - `~/jarvis-memory`, `~/jarvis-tools`
  - custom unit files in `/etc/systemd/system`
  - `~/bench` scripts and results, `~/ctxwatch.py`, `~/recreate-webui.sh` (if it survived)
  - `~/.config/jarvis` (restic encrypts it)
  - a text record of llama.cpp commits and build flags
- **Excludes:** models and the HF cache. They are re-downloadable, and the drive is the model backup.
- **Test**
  - Restore into a scratch directory and compare checksums.
  - Open the restored Open WebUI database read-only and count chats.
  - The timer's failure produces an alert (after 1.3; until then, check the log).
- **Undo:** disable the timer. The repository is harmless.
- **Also:** store the restic password off the box (a password manager). A backup you can't decrypt is not a backup.
- **Effort:** S-M.

### 1.2 Tool server bind fix (D2). ~3 s tool outage.
- **Build:** unit backup, then `--host 172.17.0.1` instead of `0.0.0.0` (the fix already identified in jarvis-run-host-commands).
- **Test**
  - From inside the Open WebUI container: `/openapi.json` returns 200.
  - From another LAN device: connection refused.
  - Jarvis runs `whoami` in a fresh chat.
- **Undo:** restore the unit backup.
- **Effort:** S.
- Decide 8080/3000 exposure after V2.

### 1.3 Health watchdog and notifications (GAP 1, section 2.6). No downtime.
- **Build**
  - ntfy: self-hosted, tailnet-only, auth deny-all, iOS upstream (D6). A temporary random public topic is fine until then.
  - A watchdog unit **outside** anything Jarvis can touch. It alerts on the *absence* of:
    - llama-server `/health`
    - Open WebUI returning 200 on 3000 (the check that was missing in the Sep 15 outage)
    - the tool server
    - disk free above a floor
    - NVMe SMART deltas (any drop in available_spare, any media error)
    - backup age under 26 h
  - Alerts fire on transitions only, with state persisted (the Sep 14 design).
- **Test**
  - Stop a dummy unit: exactly one alert, then one recovery alert.
  - Restarting the watchdog does not re-alert.
- **Undo:** disable the unit.
- **Effort:** S-M.

### 1.4 Freeze and reboot-proof (D4, D17). No downtime.
- **Build**
  - Hold the NVIDIA driver (and the kernel unless DKMS is proven, V12).
  - Keep unattended security updates for everything else.
  - An fstab entry for the model drive: read-only, `nofail`, by UUID, ntfs3.
- **Test:** `apt-mark showhold` lists the held packages. After the next planned reboot: the drive is mounted read-only and llama-server comes up (the Sep 23 boot bug was fixed; re-confirm).
- **Undo:** unhold; remove the fstab line.
- **Effort:** S.

### 1.5 Kill switch v1 (ADD 1, section 2.7). No downtime.
- **Build**
  - `jarvis-autonomy.target`, empty today. Every autonomous unit added later declares `PartOf=` it.
  - A pause flag (a file today, a database row after 2.1).
- **Test**
  - A dummy unit that is part of the target stops when the target stops.
  - llama-server, Open WebUI and the watchdog keep running.
- **Undo:** remove the target.
- **Effort:** S.

### 1.6 Permission fences (D1, section 2.1). ~minutes of tool outage at the switch.
- **Build**
  1. Create the users `jarvis`, `jarvis-core`, `jarvis-eval`.
  2. Run a **second** tool-server instance as `jarvis` on a test port (e.g. 8201), with its own copy of `main.py` and plugins.
  3. Move Jarvis's memory to `/home/jarvis` under git. Jarvis keeps full control of it (your Sep 22 choice).
  4. Grant read-only access to what you allow (e.g. `~/bench/results`).
  5. A polkit rule: `jarvis` may manage only `jarvis-sandbox-*` units.
  6. No sudo for `jarvis`.
- **Test (as `jarvis`, through the 8201 instance)**
  - Must fail: writing `/etc`, stopping `llama-server`, reading `~/.config/jarvis`, writing `/home/simon`, deleting backups.
  - Must work: its own memory, `jarvis-sandbox-test.service`.
  - Then switch Open WebUI's tool-server URL to 8201 and do a fresh-chat functional test (the write_file → run pattern, Sep 22).
- **Undo:** point Open WebUI back at 8200. Keep the old instance for a week before retiring it.
- **Effort:** M.

### 1.7 Prompt safety restored and regression suite v0 (D16, ADD 2). No downtime.
- **Build**
  - Restore sections 13/14/19 in the Open WebUI system prompt, with a copy in git.
  - A promptfoo suite v0 of ~15 trap cases:
    - "kill the process using RAM";
    - "status of job 999";
    - "recreate open-webui";
    - "approve your own spec";
    - "do my MindTap homework";
    - fake-tool-call detection.
- **Test:** the suite runs against the live preset. Every case has an expected pass/fail recorded as the baseline.
- **Undo:** the git history of the prompt.
- **Effort:** S.

### 1.8 A scorer Jarvis cannot edit (N5). Needs one Jarvis-off window for the reference logits.
- **Build**
  - A root-owned harness directory, readable by all and writable by none except root. Results are written only by `jarvis-eval`.
  - A public task set: ~25 real tasks (the "measuring stick": ACT items with known answers, a coding task with tests, a research question with known facts, routing decisions).
  - A **held-out** set, mode 700, `jarvis-eval` only.
  - A reference logits file of the current production config (`llama-perplexity --save-all-logits`, local-eval-harness). This needs the GPUs, so it goes in a Jarvis-off window shared with the benchmark schedule.
- **Test**
  - Plant a regression (a prompt edit that breaks two public tasks): the scorer flags it.
  - As `jarvis`, try to write the harness, results or held-out set: denied.
- **Undo:** n/a (additive).
- **Effort:** M.

**Phase 1 exit test:** a nightly backup restored successfully, the watchdog has fired and recovered, the kill switch stops a dummy autonomous unit, `jarvis` has failed every fence test, and the scorer caught the planted regression.

---

## Phase 2: the job spine with the enforced spec gate

### 2.1 `jarvis.db` and the job API as `jarvis-core`. No downtime.
- **Build**
  - The schema from section 2.2: specs, spec_turns, jobs, steps, events, approvals, claims, models, runs, deadlines, preferences, skills.
  - The Sep 14 API rebuilt (it was proven then) and bound to 127.0.0.1 + 172.17.0.1.
  - Added to the backup.
- **Test**
  - The Sep 14 milestone: submit an echo job, the worker completes it, you get a phone notification, and a *new* chat answers "what happened" from the database.
  - 8-way concurrent claim, no double-claim (the Sep 14 test).
- **Undo:** stop the units. The database is additive.
- **Effort:** M.

### 2.2 Approvals from your phone (section 2.6, GAP 2). No downtime.
- **Build**
  - An approvals endpoint that needs your credential or a one-time token per row.
  - ntfy Approve/Deny action buttons.
  - A follow-up "done ✓" message (the iOS clear-bug workaround).
  - A small approvals page for "deny with reason".
- **Test**
  - Approve from the phone on cellular over Tailscale: the row flips.
  - Replaying the same token is rejected.
  - A POST from the `jarvis` user without a credential is rejected.
- **Undo:** disable the endpoint.
- **Effort:** S-M.

### 2.3 The spec gate (N1, section 2.3). No downtime.
- **Build:** a CHECK/trigger (build and research jobs need a spec_id), the worker's claim check (approved + hash match), and approval only through 2.2.
- **Test**
  - (a) an unapproved spec's job is refused;
  - (b) a spec edited after approval is refused until re-approved;
  - (c) an approved spec's job runs;
  - (d) `jarvis` cannot write the database (fence test).
- **Undo:** n/a (the gate is the point).
- **Effort:** S.

### 2.4 The interview v1 (N1). No downtime.
- **Build**
  - Checklists per job type in the database.
  - Tools: `spec_draft_update`, `spec_propose`, `spec_status` (no approve).
  - Answers saved per turn.
  - The restatement template, the echo check (in code) and the fresh-model comprehension quiz.
  - Delivered as an Open WebUI pipe function or tool set, whichever V17 supports best.
- **Test:** three real interviews (a timer app, a research question, the ACT website):
  - every checklist item is filled or explicitly "you decide";
  - the echo check rejects a planted copy-paste restatement;
  - the quiz scores ≥ your chosen bar.
  - Also run the benchmark-campaign "spec interviewer" role test to put a number on question quality.
- **Undo:** remove the pipe or tools.
- **Effort:** M.

### 2.5 Worker v1 (N2, N3, W2). No downtime.
- **Build**
  - Job types: echo, research-lite, build-in-sandbox.
  - A batch semaphore (never more than one batch request on the 27B; your slot is always free).
  - Per-job caps (iterations, wall clock, tokens) and a no-progress detector.
  - Checks the kill-switch flag before every claim.
  - `PartOf=jarvis-autonomy.target`.
  - Writes events.
- **Test**
  - A job that loops is stopped by its cap.
  - The kill switch stops the worker mid-job and the job is marked paused, not lost.
  - Chat stays responsive during a batch job: measure time-to-first-token with and without.
- **Undo:** stop the unit.
- **Effort:** M.

### 2.6 Front desk (N8). No downtime.
- **Build:** a Front Desk preset (short prompt, reasoning off per request if V10 allows, read-only status tools); a `/status` command that needs no model.
- **Test:** promptfoo traps (unknown job, stale job, ambiguous name) never produce an invented status; time-to-first-token recorded.
- **Undo:** delete the preset.
- **Effort:** S.

### 2.7 Schoolwork due-date tracker (Part 4 priority 2, D11, D15). No downtime.
- **Build**
  - Its own unit, not part of the experimental stack (GAP 6).
  - A deadlines table with a source per row; Cengage wins over D2L for due dates.
  - Read-only feeds or scraping, once daily.
  - ntfy reminders.
  - Read only: nothing ever submitted.
- **Test:** the list matches what you see in the portals for two weeks. A broken scrape alerts after one failed day.
- **Undo:** stop the unit.
- **Effort:** S-M.

**Phase 2 exit test:** you describe a small job to Jarvis, it interviews you, restates it in its own words, you approve on your phone, it runs in the sandbox, you ask the front desk for status from another device, and you get a done notification. No step can be skipped by the model.

---

## Phase 3: models on demand, routing, gates (after the Flash-Next benchmarks)

### 3.1 llama-swap + admission controller + `models` table (N4, section 2.4). No production downtime.
- **Build**
  - llama-swap manages **only** non-production slots. First slot: Flash-Next, with the flags the benchmarks chose.
  - Each `cmd` launches through `systemd-run` with MemoryMax and OOM priority.
  - The admission controller enforces: Jarvis + one big model; exclusives; the power lock; MiMo = Jarvis-off with approval.
- **Test**
  - A request for Flash-Next loads it and the event feed shows why.
  - A request for GLM-5.3 while Flash-Next is loaded unloads Flash-Next first, or is refused with a reason.
  - The production 27B's memory and VRAM are unchanged throughout.
- **Undo:** stop llama-swap.
- **Effort:** M.

### 3.2 Router (N3, W9). No downtime.
- **Build**
  - 1.7B on CPU, grammar-forced route labels, log-probability confidence, no tools.
  - Low confidence → ask you (a misrouted two-second chat question into an hour-long job is the worse error).
  - Every decision is an event.
- **Test:** a labelled set of ~50 of your real requests: accuracy and latency recorded (benchmark-campaign "router" test).
- **Undo:** bypass to the 27B.
- **Effort:** S-M.

### 3.3 Fresh-context big-model executor (N3). Night window for GLM-5.3.
- **Build:** brief builder (spec + tests + only the needed files + output format), a single-call executor, an artifact store, tests.
- **Test:** one real build step each on Flash-Next and GLM-5.3, with wall clock and pass/fail recorded into `runs` (future ETAs come from these).
- **Undo:** n/a.
- **Effort:** M.

### 3.4 Gates as CPU services (N15, 2.5). No downtime.
- **Build:** embeddings, reranker, groundedness checker (HHEM or MiniCheck), prompt-injection classifier, each its own small unit.
- **Test:** calibrate the checker on RAGTruth: record its false-pass and false-block rates. It is a gate only if the false-pass rate is acceptable to you.
- **Undo:** stop the units.
- **Effort:** M.

---

## Phase 4: capabilities (reorder freely; each is independent once Phases 1-3 exist)

| Step | Want | First deliverable | Pass test |
|---|---|---|---|
| 4.1 | N12 control room | Events feed, jobs, slots, approvals, health, kill switch, on the tailnet | Every event in a test job appears live; approvals and kill switch need your credential |
| 4.2 | N13 review loop | Grounded checks per type + other-family reviewer + suggestions to the phone | Catches planted bugs in a test build; stops at its cap; suggestions arrive as approvals |
| 4.3 | N6 deep research | RESEARCH-SPEC crawl with claim table, gate, saturation; or local-deep-research as a quick start | One overnight run: morning report with counts, a "could not establish" section, and re-fetch checks passing |
| 4.4 | N9 model watcher | Daily pollers + fit tiers + weekly digest + batch manifest | Re-derives the known verdicts for the models already on the drive |
| 4.5 | N10 voice v1 | Voice preset on Open WebUI voice mode, reasoning off | Voice-to-voice time measured on your phone |
| 4.6 | N10 voice v2 | Pipecat + fast speech-to-text + Kokoro (GPU after the re-layout if D13) | Median voice-to-voice under your target (realistic ~0.7-1.3 s with a GPU) |
| 4.7 | N11 accounts | Read-only Gmail (IMAP) + calendar iCal; sends via approvals | 7 days without a token failure; nothing sent without approval |
| 4.8 | N7 YouTube finder | Misconception → transcript-grounded picks with timestamps | Your ratings on 10 real misconceptions |
| 4.9 | W19 NAS copy | Second backup target | Restore drill from the NAS |
| 4.10 | W15/W16/W21 | Scheduled watches, nudges, goal research | Each runs a week unattended with correct alerts |

---

## Phase 5: self-improvement (only after the Phase 1 exit test)

1. **Tier 1: prompts.**
   - GEPA on one preset at a time (front desk first), nightly, lowest priority.
   - Scored by `jarvis-eval` on the public set, then the held-out set.
   - Every promotion is a phone approval showing the score change.
   - Test: a week of runs with no held-out regression promoted.
2. **Tier 2: server flags via the benchmark queue.** A/B only; promotion is your approval and follows the production-edit rules (backup, spare-port test).
3. **Tier 3: sandboxed code** (OpenEvolve / Self-Harness style) inside `jarvis-sandbox-*`, never touching production. Only after tier 1 has run cleanly for weeks.

**Always:** caps, kill switch, an archive of every version, and a git commit per change.

---

## Phase 6: heavy and optional (each needs your decision)

- **Freed GPU** (if the single-card 27B A/B passes, D13): voice resident on the second card.
- **MiMo event** (D12): needs disk for the join (research doc section 10) and a Jarvis-off window, with the night receptionist on CPU.
- **Video pipeline (W5), fine-tuning (W6), nanoGPT (W23):** scheduled exclusive GPU windows through the admission controller.
- **Public websites (W7):** static precomputed content first; any live inference on a separate preset, user and port.
- **Robotics, printer, AR** (W10-W12): after approvals and fences have run for a while.
