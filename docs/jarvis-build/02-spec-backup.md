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
