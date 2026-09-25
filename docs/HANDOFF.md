# Handoff — Jarvis / jarvis-1 work (as of 2026-09-25 ~01:30 UTC)

You are picking up from a previous Claude Code session. Read this whole file before doing anything.

## Who and what
- The user is **Simon**. Always call him Simon. Older notes (the Cowork memory pages in `docs/wiki/`) call him "Jack" — same person; never use "Jack" in anything you write for him or for Jarvis. ("Jackrong" is a Hugging Face uploader name, not him.)
- **Jarvis** is Simon's local AI assistant: Qwen3.8-27B served by llama.cpp (`llama-server.service`, port 8080) on his home server **jarvis-1** (2x Tesla V100-PCIE-16GB, 2x Xeon E5-2699 v3, 503 GiB RAM, Ubuntu 24.04), used through Open WebUI (port 3000). Jarvis has an unrestricted shell tool server (port 8200) with endpoints run_host_command, write_file, read_file, save_finding, web_search, hf_model_sizes, create_tool, list_tools, plus plugins gpu_status, memory_search, sys_summary.
- **You cannot reach jarvis-1.** Everything on the box goes through Simon: you write commands, he pastes them into an SSH terminal and pastes the output back. He also relays messages between you and Jarvis by hand.

## Where everything is (this repo, branch `claude/new-session-uyo1y3`)
If your session is on another branch: `git fetch origin claude/new-session-uyo1y3` and read the files from it (or check it out if you'll be committing there).
- `docs/jarvis-briefing-2026-09-25.md` — Part 1-3 of the briefing written for Jarvis: the box, live server config, tools, rules, downloads, big-model run recipes, plans, dead ends, priorities.
- `docs/jarvis-briefing-2026-09-25-part4.md` — what Simon wants (24 wants), hard boundaries, learning protocol, self-improvement plan, corrections to Part 1.
- `docs/jarvis-briefing-2026-09-25-part5.md` — facts VERIFIED on the box by survey; wins over Parts 1-4 on conflicts.
- `docs/jarvis-survey.sh` — read-only survey script (Simon has it at `~/jarvis-survey.sh`; output in `~/jarvis-survey.txt`).
- `docs/wiki/` — 34 Cowork memory pages copied verbatim (index in `docs/wiki/README.md`). These are the source for everything in the briefing. `v100-hardware-and-models.md` = the Cowork page "local-model-landscape".
- `docs/jarvis-progress.md`, `docs/fast-house-download.md` — earlier summaries (Sep 24).

## What was done this session
1. Imported Simon's Cowork memory export and four pasted pages into `docs/wiki/`.
2. Wrote the briefing for Jarvis (Parts 1-3, then Part 4 and Part 5), cross-checked every number and claim against the wiki pages, and corrected it against a live survey of the box.
3. Delivery lesson: having Jarvis save a long file through write_file FAILED (tool-call JSON broke at an apostrophe, column 357). The 27B drops quotes in long tool-call strings. Deliver files to the box as a terminal heredoc Simon pastes: `cat > FILE <<'UNIQUE_END' ... UNIQUE_END` (quoted delimiter), then verify with `wc -l`, `wc -c` and `sha256sum | cut -c1-16`. His terminal display garbles long pastes, but the file lands intact — trust the checksum, not the echo.

## State of the box (survey 2026-09-25 01:00 UTC)
- Running: llama-server, jarvis-run-host-commands, gpu-tune, jarvis-perf, nvidia-persistenced. nvidia-powercap inactive (intended).
- GONE since the Sep 21 rebuild: the job API/worker/ntfy notifier/healthcheck, supervisor, embedding server, ACT tool server. Nothing listens on 8110/8100/8102/8103/8090.
- llama-server runs under `numactl --cpunodebind=0 --membind=0` (the rest of ExecStart was not captured; Part 1 has the config from notes: f16 KV, -c 24576, -ts 28,36, -devd CUDA0, --parallel 2, --kv-unified, xhigh, --spec-draft-p-min 0.4, MTP draft n-max 5).
- Tool server binds 0.0.0.0:8200 (unrestricted shell on the LAN). Suggested fix `--host 172.17.0.1`, not done.
- Driver 580.178.04, NOT held by apt. ECC disabled on both GPUs (buys nothing; notes recommend re-enabling). Power limit 200 W.
- Jarvis's Open WebUI system prompt is only 367 chars; safety sections §13/§14/§19 are MISSING. Model row: temperature 0, num_ctx 24576, function calling native, builtin_tools False.
- Tailscale: no serve config (nothing published). Boot NVMe healthy (100% spare, 0 errors). One `truncated = 1` context overflow since boot.
- llama.cpp build supports qwen4exp, glm-dsa, hy_v4, mimo2, deepseek4; NOT glm5next (GLM-5.3-Flash needs the Unsloth fork).
- Jarvis's memory (`~/jarvis-memory/`): state.md (STALE, Sep 21 config, calls Simon "Jack"), log.md, operating-manual.md (has the guardrails, calls Simon "Jack"), findings/*.md (save_finding / memory_search), and the briefing files.

## What Simon has done / not done (as far as known)
- DONE: saved briefing Part 1-3 (`~/jarvis-memory/briefing-2026-09-25.md`, 26,612 bytes, sha256 prefix 230ee4de59c4058d — the version BEFORE the "Jackrong" rewording) and Part 4 (9,222 bytes, matches repo). Pointer lines added to state.md. Ran the survey.
- CHECKED Sep 25 ~03:45Z: Part 1-3 on the box is still the pre-Jackrong-fix version (26,612 B, 230ee4de59c4058d). Part 4 matches (7dd4fa07d462a1e5). Part 5 NOT saved. Driver NOT held (showhold empty).
- Part 5 was updated in the repo (48 lines, 6,079 B, hash 1e5775436aea51a0): hardware identity settled, model-drive section added. Delivery of it + the Jackrong fix (a small python replace script, result must hash 794606f5864d29df) was handed to Simon; confirm it landed.
- NOT YET DONE: safety block in the system prompt; pinning the driver; sending Jarvis the "read the briefing files" message; revoking the HF token that sits in plain text on the model drive.

## Model drive (plugged into jarvis-1 on Sep 25)
- 4 TB SkyHawk, USB, NTFS label Models, /dev/sda2, mounted READ-ONLY at /mnt/models (not in fstab yet). Content in /mnt/models/models/, 2.7 TB used, 1.1 TB free. Download chain was stopped with STOP-CHAIN.txt; no errors in chain.log.
- Folder sizes: MiMo 522G (still two raw parts, not joined), GLM-5.3 437G, GLM-5.3-Flash 188G, Flash-Next unsloth 128G, GSQ-RCO IQ3_XXS 71G, Q2_0 62G, HauhauCS 27B 35G, 27B-MTP 29G, Coder-Next 34G, VL-32B 20G, gpt-oss-20b 13G, corpus 577G, audio 208G, video 182G, train 98G, data 28G, image 20G, embed 14G, slots 9G.
- Verify: verify.py copied to ~/model-verify/ with ROOT=/mnt/models/models and LOGDIR=~/model-verify/_logs (drive stays read-only). Size-only: 53/53 files OK. Full sha256 started in background (~1.45 TB, ~2-2.5 h, output ~/model-verify/full.out). verify.py only covers 9 repo folders; 27B-MTP, Coder-Next, VL-32B, embed, audio, video, image need a second pass.
- The drive carries the Cowork session's JARVIS-BRIEFING.md, MANIFEST.md, BUILD-QUEUE.md (Tasks 0-9, Task 0 = backup), RESEARCH-SPEC.md, HANDOFF-PROMPT.txt. Its HANDOFF-PROMPT has wrong paths (/mnt/models/X instead of /mnt/models/models/X) and says "never write to the drive" while Task 0 puts restic on it. Its rule "don't copy the drive to NVMe; serve from HDD" is sensible; Claude agreed to follow it for now.
- Backup target decision asked of Simon: (a) drive rw only during backup, (b) NAS, (c) drive now, NAS later (recommended).

## Open questions / conflicts to resolve next
1. SETTLED Sep 25: jarvis-1 = HYVE G2GPU12, Z10PG-D16 Series, BIOS 3803. The ESC4000 G3 is the NAS. Old question was: **Which machine is jarvis-1?** Jarvis's own finding says jarvis-1 is a **HYVE G2GPU12** (Z10PG-D16 board) and the **ASUS ESC4000 G3 is a separate machine Simon is setting up as a NAS** (8 hot-swap bays, needs caddy part 13GS1I0AM063-1). The Cowork notes call jarvis-1 the ESC4000 G3 throughout. Board/CPU facts hold either way; chassis facts (PSU derating, GPU power harness, "max 4 GPUs", ASUS CPU support list/BIOS versions in gpu-upgrade-options and system-performance-levers) may not. Settle with `sudo dmidecode -s system-product-name; sudo dmidecode -s baseboard-product-name; sudo dmidecode -s bios-version`.
2. **Backup (Simon's #1 priority, WANT 19):** no off-box backup exists. The NAS is the natural target.
3. Missing Cowork pages Simon may transfer: model-pull-and-flags, model-storage-plan, local-ai-setup, jarvis-backup, nvme-drive-failure, quant-quality-tables, model-tier-ceiling, glm-5.3-download, fast-house-extras, learning-partner, esc4000-parts-order, and any page updated after Sep 24. Save new pages into `docs/wiki/` verbatim (header: copied date, last-updated, summary; convert Cowork links to plain page names; redact the ntfy topic as `<ntfy-topic>`; never store keys) and update `docs/wiki/README.md`.
4. Whether the fast-house download finished (state known only to Sep 24 14:00Z, ~1,821 GB done).

## Rules for working with Simon and Jarvis
- Accuracy over reassurance: label MEASURED / ESTIMATE / VERIFY; say plainly what you have not checked. A correction is a claim, not a verdict — re-read the source.
- Never tell Jarvis (or Simon) to pkill/killall, restart or recreate the open-webui container, or edit the production llama-server unit without a backup and a test on a spare port. Anything that could cut Simon off from Jarvis must be stated plainly first.
- Changes to the box are Simon's decisions. Recommend; don't assume.
- Never do Simon's graded schoolwork (his own rule).
- Keep files meant for Jarvis in plain ASCII-friendly text; deliver them by terminal heredoc, not through Jarvis's write_file.
- Commit and push to `claude/new-session-uyo1y3`. No model identifiers in commits or files.
