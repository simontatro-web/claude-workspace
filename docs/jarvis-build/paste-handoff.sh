mkdir -p ~/jarvis-build/handoff && cd ~/jarvis-build/handoff
cat > 00-START-HERE.md <<'JBH_END'
# Jarvis build mission (from Simon, written by Claude, 2026-09-25)

Simon is out of Claude usage. You (Jarvis) build the first pieces of his orchestrator plan yourself, one small step per chat, while he supervises. Call him Simon.

## Every chat, in this order
1. Read this file, then ~/jarvis-build/PROGRESS.md (create it if missing), then 01-steps.md.
2. Take the FIRST unfinished step in 01-steps.md and read its spec file.
3. Tell Simon in 3-5 lines what you will build and how you will test it. Wait for his OK.
4. Build it in ~/jarvis-build/<step>/. Use write_file for any multi-line file (never heredocs). Keep each file small.
5. Run its tests. Paste the real test output summary; never claim a pass you did not see.
6. Commit: ~/jarvis-build is a git repo (git init it on first use). One commit per working change.
7. Update PROGRESS.md: done / test result / next / FOR SIMON (commands he must run, each with a test and an undo).
8. Stop when the step is done or the chat is getting long (about 15 tool calls). Simon starts a fresh chat for the next step.

## Hard rules (these protect the server you run on)
- NEVER run: sudo, apt, snap, lxc, lxd, docker, pkill, killall, reboot, shutdown.
- NEVER start, stop, restart or edit any systemd unit. Never touch llama-server, Open WebUI, the tool server (~/jarvis-tools), ~/.config/jarvis, ~/bench, ~/models, /etc.
- Only kill a process you started yourself in this step, by the PID you recorded.
- Test servers bind to 127.0.0.1 only, ports 8110-8119.
- Python: use a venv at ~/jarvis-build/venv (python3 -m venv). pip install only into that venv.
- Anything that needs root: write the exact commands under FOR SIMON in PROGRESS.md, with what it changes, a test, and an undo. Simon runs them after checking.
- Loops: if the same fix fails 3 times, stop and write down exactly what is failing. Max 10 tool calls per turn.
- Facts about the box: check with a read-only command, do not guess. Say "measured" or "not checked".
- Never do Simon's graded schoolwork.

## What the finished plan looks like (for context only)
A job queue in SQLite that refuses to run any build job without a spec Simon approved; workers that run jobs with hard caps; a kill switch; approvals from his phone; health alerts; nightly off-box backups. The full design is in the Claude repo (docs/orchestrator-research.md, docs/orchestrator-roadmap.md); you do not need it to do your step.
JBH_END
cat > 01-steps.md <<'JBH_END'
# Build steps, in order (Jarvis builds; Simon runs anything needing root)

Status lives in ~/jarvis-build/PROGRESS.md, not here.

| Step | What | Spec | Who installs |
|---|---|---|---|
| S1 | Backup script (restic, SQLite-safe), tested against a local test repo | 02-spec-backup.md | Simon installs the timer and the real target later |
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
cat > 02-spec-backup.md <<'JBH_END'
# S1 spec: backup script

Goal: one command that makes an encrypted, restorable snapshot of everything Jarvis cannot re-download.

Files: ~/jarvis-build/backup/jarvis-backup.sh (bash) and sqlite_snap.py (python, stdlib only), config.env.

config.env (plain KEY=VALUE, sourced by the script):
- RESTIC_REPOSITORY (test: ~/jarvis-build/backup/test/repo)
- RESTIC_PASSWORD_FILE (test: ~/jarvis-build/backup/test/pass.txt, make it yourself; NEVER use or read ~/.config/jarvis/restic-pass)
- SOURCES: space-separated paths. Real list (Simon fills later): /home/simon/jarvis-memory /home/simon/jarvis-tools /home/simon/jarvis-build /etc/systemd/system /home/simon/bench /home/simon/ctxwatch.py
- SQLITE_DBS: space-separated live SQLite files to snapshot safely (real: jarvis.db later, Open WebUI's webui.db path, which Simon will find)
- STATUS_FILE: where the last result is written (JSON)

What the script does:
1. For each SQLite DB: sqlite_snap.py copies it with the sqlite3 backup API (sqlite3.connect(src).backup(dst)), never cp. Then runs PRAGMA integrity_check on the copy; fail if not "ok". Copies go in a staging dir that is included in the snapshot.
2. restic backup SOURCES + staging dir, with --exclude for *.gguf, *.safetensors, .cache, venv.
3. restic forget --keep-daily 14 --keep-weekly 8 --prune.
4. Writes STATUS_FILE: {"time": ISO, "ok": true/false, "snapshot": id, "bytes_added": n, "error": text}.
5. Exit code 0 only if everything succeeded.

Tests (all must pass, paste the output):
- T1: make a test source dir with 3 small files and a test SQLite DB with 100 rows. Init the test repo. Run the script. Exit 0, STATUS_FILE ok.
- T2: restore the latest snapshot to /tmp/jb-restore-test, diff -r the files: identical; open the restored DB: 100 rows, integrity ok.
- T3: point SQLITE_DBS at a missing file: script exits non-zero and STATUS_FILE says ok false with the error.
- T4: open a write transaction on the test DB in another process while backing up: backup still succeeds and the copy passes integrity_check.

restic is installed (0.16.4). Do not install anything system-wide. Clean up /tmp test dirs after.

FOR SIMON when done: the real config values to fill in, the systemd service + timer text (nightly 02:30 America/Chicago, runs as root because Open WebUI's DB is root-owned), and the test he should run after installing.
JBH_END
cat > 03-spec-watchdog.md <<'JBH_END'
# S2 spec: health watchdog

Goal: tell Simon when something that should be running is ABSENT. Alerts on changes only (down once, recovered once), never spam.

Files: ~/jarvis-build/watchdog/watchdog.py (stdlib + urllib only), config.json, state.json (written by the script).

config.json:
- checks: list of {name, type, target, ...}. Types:
  - http: GET target, pass if status == expect (default 200) within timeout 5 s
  - disk_free: path, min_gb
  - file_age: path, max_hours (for the backup STATUS_FILE; also fail if its "ok" is false)
  - systemd_active: unit name, uses `systemctl is-active` (read-only, allowed)
- notify: {"type": "ntfy", "url": "https://ntfy.sh", "topic": "SIMON_FILLS_THIS"} or {"type": "print"}
- Real checks Simon wants: llama-server http://127.0.0.1:8080/health; Open WebUI http://127.0.0.1:3000/ ; tool server http://127.0.0.1:8200/openapi.json (Simon will change it to http://172.17.0.1:8200/openapi.json after the bind fix); disk_free / min 25 GB; file_age backup status 26 h; systemd_active llama-server, jarvis-run-host-commands.

Behaviour:
- Modes: --once (one cycle, for tests) and default loop every 60 s.
- First cycle: send one DOWN for each check that is already failing; say nothing about passing checks.
- On a check going pass->fail: one alert "DOWN: name: reason". fail->pass: one alert "RECOVERED: name". Unchanged: nothing.
- state.json written atomically (write tmp, rename), so a restart does not re-alert.
- Every cycle wrapped in try/except: one broken check never kills the loop; a check that raises counts as failed with the error text.
- ntfy send: POST to url/topic with the message; priority 5 for DOWN, 3 for RECOVERED. Failure to send is logged, not fatal.

Tests (use notify type print; paste output):
- T1: one http check to 127.0.0.1:8119 (nothing listening). --once: exactly one DOWN. --once again: nothing. Start a tiny test server (python3 -m http.server 8119 --bind 127.0.0.1, record its PID). --once: exactly one RECOVERED.
- T2: with the test server up, delete state.json, --once: nothing; kill ONLY your recorded PID; --once: exactly one DOWN; --once again: nothing; restart server; --once: exactly one RECOVERED.
- T3: disk_free with min_gb 999999: fails with a clear reason.
- T4: a check type that raises (bad config): loop survives, reported as failed.

FOR SIMON when done: the systemd unit text (runs as simon for now, Restart=always, NOT part of any autonomy target), and how to put his ntfy topic in config.json.
JBH_END
cat > 04-spec-jobdb.md <<'JBH_END'
# S3 spec: job database + API with the spec-approval gate

Goal: the core rule of Simon's plan: no build or research job can run unless Simon approved its spec, and a spec edited after approval is automatically unapproved. Enforced in the database and the API, not by asking a model.

Files: ~/jarvis-build/jobdb/schema.sql, db.py, api.py (FastAPI + uvicorn in the venv), test_gate.py (pytest).

Tables (SQLite, WAL, foreign_keys ON):
- specs(id, title, job_type, status CHECK in (draft, proposed, approved, superseded), body_md, approved_sha256, approved_at, created_at, updated_at)
- spec_turns(id, spec_id, role CHECK in (jarvis, simon), text, created_at): every interview question and answer, saved as it happens
- jobs(id, spec_id NULL, type, status CHECK in (queued, running, done, failed, paused), payload_json, result_json, max_seconds, created_at, claimed_at, finished_at)
- events(id, time, source, kind, job_id NULL, message): append-only log
- approvals(id, kind, ref_id, status CHECK in (pending, approved, denied), token_sha256, created_at, decided_at, reason)

Gate rules (all three must exist):
1. Trigger: INSERT into jobs with type in (build, research, self_change) and spec_id NULL -> RAISE(ABORT).
2. Claim (POST /jobs/claim): claims the oldest queued job ONLY if it has no spec (type echo) OR its spec status = approved AND approved_sha256 = sha256(body_md). Claim is one atomic UPDATE ... RETURNING under a lock (no double claims).
3. Approval: POST /specs/{id}/approve requires header X-Approve-Token matching the one-time token of a pending approvals row for that spec (store only its sha256). On success: status approved, approved_sha256 = sha256(body_md), token row marked used. A reused or wrong token -> 403.
Also: PUT /specs/{id} (edit body) sets status back to draft if it was approved.

Other endpoints: POST /specs, POST /specs/{id}/turns, POST /specs/{id}/propose (creates the pending approval, returns the token ONCE; later Claude will route it to Simon's phone), POST /jobs, GET /jobs/{id}, GET /status (counts per status + last 20 events), GET /health. Every state change writes an event.

Run: uvicorn on 127.0.0.1:8111 only. DB file: ~/jarvis-build/jobdb/test.db for tests.

Tests (pytest, paste the summary line):
- build job without spec -> rejected
- job with draft spec -> never claimed
- approve with wrong token -> 403; with right token -> approved; same token again -> 403
- edit approved spec -> back to draft -> its job no longer claimable
- approved spec job -> claimed exactly once
- 8 concurrent claim calls on 5 echo jobs -> 5 distinct claims, 3 "nothing to claim", 0 errors
- /status returns counts that match the rows

Known limit (write it in PROGRESS.md): until Simon creates the separate users, Jarvis's shell could edit test.db directly. The gate becomes unbreakable only after that step. Do not work around the gate yourself.
JBH_END
for f in *.md; do echo "$f $(wc -l < $f) $(wc -c < $f) $(sha256sum $f | cut -c1-16)"; done; cd ~
