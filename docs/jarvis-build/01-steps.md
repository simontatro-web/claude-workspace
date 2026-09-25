# Build steps, in order (Jarvis builds; Simon runs anything needing root)

Status lives in ~/jarvis-build/PROGRESS.md, not here.

| Step | What | Spec | Who installs |
|---|---|---|---|
| S1 | Backup script (restic, SQLite-safe), tested against a local test repo | 02-spec-backup.md | Simon installs the timer and the real target later |
| S1b | Context-watch filter for Open WebUI (warns before the context overflows) | 05-spec-context-filter.md | Simon pastes it into Open WebUI |
| J1 | Jarvis Builder preset: system prompt, reply cap, filter | 07-builder-prompt.md | Simon (Open WebUI settings) |
| J2 | delegate tool: fresh-context thinking | 08-spec-delegate-tool.md | Jarvis via create_tool |
| J2b | delegate fix-up: 8000 cap, empty answer at cap, ~ paths, log location | 08-spec-delegate-tool.md (J2b section) | Jarvis via create_tool |
| J2c | Live check P4b: do the two slots share one KV pool? | 08-spec-delegate-tool.md (J2c section) | Simon drives, Jarvis records |
| J4 | replace_in_file tool: exact small edits without shell quoting | 10-spec-edit-tool.md | Jarvis via create_tool; Simon adds one line to the Builder prompt |
| J3 | Context proxy v2: BUILT BY CLAUDE in ~/jarvis-build/ctxproxy (51 tests). Do NOT rebuild or edit it. Only help Simon run ctxproxy/README.md when he asks | ctxproxy/README.md | Simon installs and runs the acceptance runs |
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
