# Master plan: everything Simon wants, built and live on jarvis-1

Written 2026-09-25 (Chicago) by Claude, for Simon and the next Claude session. Jarvis does not read this file
(his context is too small); his list is 01-steps.md. Claude changes a Status only from output Simon pasted.
Labels: MEASURED (pasted output, or run in Claude's own sandbox, and it says which), SOURCE (a doc), ESTIMATE, VERIFY.

## 1. How nothing gets lost

Three files, three jobs:

| File | Read by | Holds |
|---|---|---|
| this file (repo) | Simon, Claude | every want -> a step, in order, with status and proof |
| 01-steps.md (repo, copied to ~/jarvis-build/handoff/) | Jarvis | only his next few steps, each pointing to a spec |
| ~/jarvis-build/PROGRESS.md (box) | Jarvis, Simon | live status; the RESUME HERE block at the top |

A step is DONE only when all six hold, each with pasted output:
1. Its tests pass: the summary line itself (e.g. `51 passed`), never a description of it.
2. Committed: `git -C ~/jarvis-build show --stat HEAD` lists its files.
3. Installed where it runs: unit enabled and active, tool listed, or preset saved.
4. A live test on the real system passes.
5. It comes back by itself after a restart of its service, and after the next planned reboot.
6. It is in the backup and, once S2 exists, the watchdog checks it.

Status words: todo -> spec -> built -> installed -> DONE.

Two more rules:
- Anything that runs as root runs from a root-owned copy (/usr/local/sbin, /etc/...), installed only after
  Claude reviewed the exact diff. Never a root unit that runs a file Jarvis can edit (the S1 review finding).
- Guards are not built by what they guard: the spec gate, approvals, fences, kill switch and scorer are
  written by Claude, or reviewed line by line by Claude before install.

## 2. The loop for every step

1. Claude writes the spec (tests + undo) or the code and pushes it to claude/orchestrator-research.
2. Simon moves it to the box: GitHub "Download raw file", `scp $HOME\Downloads\<file> simon@jarvis-2:~/`,
   `sha256sum` must match Claude's value, then extract. Each bundle carries the handoff files it changes.
3. Either Jarvis builds it in a NEW Jarvis Builder chat, opener:
   "Read ~/jarvis-build/PROGRESS.md (RESUME HERE), then ~/jarvis-build/handoff/01-steps.md. Tell me the next
   step and how you will test it, then wait for my OK."
   Or Simon runs Claude's root steps, each with what it changes, a test and an undo.
4. Simon pastes the proof: test output, `git -C ~/jarvis-build show --stat HEAD`,
   `git -C ~/jarvis-build status --short`, and for installs `systemctl status <unit> --no-pager | head -5`.
5. Claude checks it, updates this file, and writes the next step. Never tick from a summary: Jarvis has
   claimed changes he did not make.

When Claude must read code Jarvis wrote (every security piece, and before each stage gate):
`git -C ~/jarvis-build archive --format=tar.gz -o ~/jb-review.tgz HEAD` (committed files only: no venv,
nothing untracked), check `tar -tzf ~/jb-review.tgz | head -50`, scp it to the PC, and upload it on GitHub to
docs/jarvis-build/from-box/ on this branch. The repo is private (MEASURED, GitHub API, 2026-09-25).

Start of every Claude session, Simon pastes this (read-only):

    git -C ~/jarvis-build log --oneline -5; git -C ~/jarvis-build status --short
    head -20 ~/jarvis-build/PROGRESS.md
    systemctl is-active llama-server jarvis-run-host-commands jarvis-ctxproxy

`git status` must be empty. Anything listed changed without a commit: until the fences (R1.6), Jarvis's
shell can edit every file Simon owns, the proxy included.

## 3. The order

Each stage ends in a gate. The next stage starts only when its gate is MEASURED.

### Stage A: make Jarvis a builder you can rely on (now)
Order proposed 2026-09-25; Simon to confirm. Changes from the old queue: B1 moves up (A5), the Builder
prompt is updated before the acceptance runs (A3), J2b comes before gate 5 (A6, A7), and a regression run
is added (A9).

| Step | What | Builds | Installs | Status |
|---|---|---|---|---|
| A1 | J3 proxy on the box: ctxproxy/README.md steps 1-4 | Claude (done) | Simon | built: bundle 4758c4fb, 51 tests pass from a clean extract on Python 3.11 and 3.12 (MEASURED, Claude's sandbox). Not on the box |
| A2 | J3 service and Open WebUI wiring: README steps 5-6. After it, a tool-call test in Builder, not only "hi" | Claude | Simon | todo |
| A3 | J1b Builder prompt v2: the proxy's CONTEXT HIGH / COMPACTED rules replace the filter lines; turn budget re-set. Before A4, so the runs test the prompt you will actually use | Claude | Simon (Open WebUI) | todo |
| A4 | J3 acceptance, gates 2-4 (README 7): 3 PASS runs, each with 1+ compaction, one with 2+; in one run, restart the proxy once mid-run and it must still PASS; one closed-and-resumed run. Then set RESERVE from report.py | Jarvis runs, Simon drives | - | todo |
| A5 | B1 backup live: restic repo on the USB drive, root-owned copy of the S1 script, nightly timer, restore drill; plus R1.4's fstab line for the drive (read-only, nofail) so the target is there after a reboot. Runs alongside A4 (your root time, not GPU time). Today nothing on the box has a second copy (SOURCE: handoff) | Claude, from the S1 files | Simon | S1 built, tested locally (SOURCE); B1 todo |
| A6 | J2b delegate fix-up (spec 08). Recommended: Jarvis builds it (small, fully specced, real use of the proxy); Claude reviews the diff | Jarvis | create_tool | todo |
| A7 | J2c = gate 5 (P4b): delegate at xhigh in a chat past ~15k tokens; does the next turn re-read everything? Needs A6: today's 8000 cap makes xhigh delegate calls return nothing (SOURCE: handoff) | - | Simon drives | todo |
| A8 | J4 replace_in_file tool (spec 10), then its rule line in the Builder prompt | Jarvis | create_tool; Simon adds the line | todo |
| A9 | Regression: one more acceptance run with the final prompt and tools; must PASS | Jarvis | - | todo |
| A10 | Loose ends: reasoning-effort three-mode test (expect 62); purge lxd-installer (optional); restic password stored off the box; start the W22 writing folder | Simon | - | todo |

Gate A: A4, A7 and A9 PASS; a B1 restore matches; one planned reboot (your timing) brings llama-server,
Open WebUI, the tool server, the proxy and the drive mount back by themselves. Then the proxy replaces the
manual new-chat routine, and Jarvis works through the stages below.

### Stage B: the foundation Jarvis builds (01-steps.md)

| Step | What | Builds | Installs |
|---|---|---|---|
| S2 | Health watchdog + phone alerts (roadmap 1.3). Add the proxy's health URL to its checks. Needs D6 | Jarvis | Simon (unit, root-owned copy) |
| S3 | Job database + API with the spec gate, tested on 127.0.0.1:8111 (roadmap 2.1/2.3 core) | Jarvis; Claude reviews the gate | in Stage D |
| S4 | Worker v0: echo jobs only, pause flag, caps; its spec approved by Simon first | Jarvis | in Stage D |

Gate B: Claude reviews S2-S4 from a jb-review upload; the watchdog has sent one real DOWN and one RECOVERED
to your phone.

### Stage C: safety foundations (roadmap Phase 1; mostly root steps Simon runs, Claude writes)

| Step | What |
|---|---|
| R1.2 | Tool server bound to 172.17.0.1 (today it listens on every interface: MEASURED, Part 5), then a host firewall (D2). Small: can be done any evening, even during Stage A |
| R1.5 | Kill switch v1: jarvis-autonomy.target + pause flag |
| R1.6 | Fences: users jarvis / jarvis-core / jarvis-eval; tool server as jarvis on 8201 (D1) |
| R1.7 | Safety sections 13/14/19 back in the system prompt (D16) + regression suite v0 (~15 trap cases) |
| R1.8 | A scorer Jarvis cannot edit (one Jarvis-off window for the reference logits) |
| R1.1b | Off-site copy of the backup (B2 or the NAS; D3 says USB first, off-site later) |

Already done (MEASURED 2026-09-25): the 17-package driver hold (D4) and simon out of the lxd group (D22).
Gate C = the roadmap's Phase 1 exit test.

### Stage D: the job spine, where "interview me every time" becomes enforced (roadmap Phase 2)
R2.1 jarvis.db + job API as jarvis-core (installs S3) · R2.2 approvals from your phone · R2.3 spec gate
enforced · R2.4 the interview v1 (N1) · R2.5 worker v1 (installs S4, grown up) · R2.6 front desk (N8) ·
R2.7 schoolwork due-date tracker (D11, D15).
Gate D = the roadmap's Phase 2 exit test: you describe a job, Jarvis interviews you, restates it in his own
words, you approve on your phone, it runs in the sandbox, the front desk reports its status from another
device, you get a done notification, and the model cannot skip any step.

### Stage E: models on demand (roadmap Phase 3, after the big-model benchmarks)
R3.1 llama-swap + admission controller + models table (N4) · R3.2 router (N3, W9) · R3.3 fresh-context
big-model executor (N3) · R3.4 gates as CPU services (N15).

### Stage F: capabilities (roadmap Phase 4, any order)
R4.1 control room (N12, W4, W20) · R4.2 review loop (N13, W3) · R4.3 deep research (N6, W21) · R4.4 model
watcher (N9) · R4.5/R4.6 voice (N10, W1, W13) · R4.7 accounts (N11, W14) · R4.8 YouTube finder (N7, W8) ·
R4.9 NAS copy (W19) · R4.10 watches and nudges (W15, W16).

### Stage G: self-improvement (roadmap Phase 5, only after Gate C)
N2, N5, D14. Prompts first, then server flags through the benchmark queue, then sandboxed code. Every
promotion is approved on your phone.

### Stage H: heavy and optional (roadmap Phase 6; each needs your decision)
Freed GPU (D13) · the biggest RAM model (D12) · video (W5) · fine-tuning (W6, needs W22) · build your own AI
(W23) · public websites (W7) · robotics, printer, AR (W10-W12) · hardening advisor (W24).
Parked by you (Sep 14): W17, W18.

## 4. Every want has a home

| Want | Lands in |
|---|---|
| N1 interview every time, never queue an unspecced job | R2.3 + R2.4: enforced by the database, not by a prompt |
| N2 builds and improves itself | Stages A-B now (Jarvis builds from specs); self-change jobs after R2.3 + R1.8 |
| N3 fresh-context big-model jobs | R3.3 (the delegate tool is the small version today) |
| N4 any model on demand, including from the drive | R3.1 |
| N5 always-on self-improvement | R1.8, then Stage G |
| N6 overnight deep research | R4.3 |
| N7 build any tool (YouTube finder) | create_tool today; R4.8 |
| N8 fast front desk | R2.6 |
| N9 new-model watcher | R4.4 |
| N10 human-speed voice | R4.5, R4.6 |
| N11 accounts and life | R4.7 |
| N12 control room | R4.1 |
| N13 models review models, approvals on the phone | R2.2, R4.2 |
| N14 never break | Stage C, B1 (A5), S2 |
| N15 no hallucinations | grounded-claims rule (J1), status only from the database (R2.6), R1.7, R3.4 |
| W1, W13 voice, "Hey Jarvis" | R4.5, R4.6 |
| W2 two jobs at once | R2.5 |
| W3 / W4, W20 / W8 / W9 | R4.2 / R4.1 + events table / R4.8 / R3.2-R3.3 |
| W5, W6, W7, W10-W12, W23, W24 | Stage H |
| W14 / W15, W16 / W21 | R4.7 / R4.10 / R4.3 |
| W17, W18 | parked |
| W19 backup | B1 (A5), R1.1b, R4.9 |
| W22 writing capture | A10: start now; it gates W6 |
| Schoolwork due-date tracker | R2.7 |

New wants: Claude adds a row here and places it in a stage before anyone builds it.

## 5. Open decisions and the step each one blocks

| Decision | Blocks |
|---|---|
| D2 bind + firewall | R1.2 |
| D6 ntfy self-hosted or public topic | S2 going live |
| D1 what the jarvis user may read | R1.6 |
| D5 revoke the Hugging Face token on the drive | nothing; recommended now |
| D9 interview rules | R2.4 |
| D11 school portals | R2.7 |
| D7 frontier budget, D8 search APIs | R4.3 |
| D10 accounts | R4.7 |
| D19 YouTube key | R4.8 |
| D14 self-improvement scope | Stage G |
| D12, D13 | Stage H |
| D21 which printer | W12 |
| D23 OOM protection for llama-server | the next production-unit edit |

Done: D3 (USB first), D4, D22 (MEASURED 2026-09-25). Standing: D18, benchmarks keep the 1-7 AM window.

## 6. Status log (newest first; one line per change, with its proof)
- 2026-09-25: plan written. J3 bundle sha256 4758c4fbc17ec6e6636b3ddda62103f6af9b6e65512272c49208831065fd1628;
  51 passed from a clean extract on Python 3.11.15 and 3.12.3 (MEASURED, Claude's sandbox). Nothing from
  Stage A is on the box yet.
