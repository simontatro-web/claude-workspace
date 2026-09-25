# Handoff: Jarvis / jarvis-1 work (as of 2026-09-25 ~14:10 UTC)

You are picking up from earlier Claude Code sessions. Read this whole file before doing anything. Branch: `claude/new-session-uyo1y3` in simontatro-web/claude-workspace. Commit and push there.

## Who and how
- The user is **Simon**. Always call him Simon. Older notes (the Cowork memory pages in `docs/wiki/`, and files on his model drive) call him "Jack": same person, never use that name. "Jackrong" is a Hugging Face uploader, not him.
- He is in Chicago time (America/Chicago; CONFIRMED by Simon 2026-09-25). Give ALL times to him in Central (CDT = UTC-5 until Nov 1 2026, then CST = UTC-6). Box logs and llama-bench test_time are UTC: convert before quoting.
- **Jarvis** is Simon's local AI assistant: Qwen3.8-27B Q4_K_M served by llama.cpp (`llama-server.service`, port 8080, both GPUs), used through Open WebUI (port 3000, docker). Jarvis has an unrestricted shell tool server (port 8200, bound to 0.0.0.0) with run_host_command, write_file, read_file, save_finding, web_search, hf_model_sizes, create_tool, list_tools, plus plugins gpu_status, memory_search, sys_summary.
- **You cannot reach jarvis-1.** Give Simon commands to paste into its SSH terminal; he pastes the output back. He relays messages to Jarvis by hand.
- Delivering files: terminal heredoc with a quoted, unique delimiter (`cat > FILE <<'X_END' ... X_END`), then verify with `wc -l`, `wc -c`, `sha256sum | cut -c1-16`. Compute the expected numbers in your own sandbox first and tell Simon what to expect. His terminal garbles the echo of long pastes; the file still lands intact: trust the checksum. Never deliver files through Jarvis's write_file (the 27B breaks tool-call JSON on long strings).
- Long-running jobs on the box: always run them as systemd units (`sudo systemd-run --unit=NAME -p User=simon -p Group=simon ...`). nohup is NOT enough: rsync overrides SIGHUP and died when Simon's SSH session dropped. Simon's own computer does turn off.

## Rules
- Accuracy over reassurance. Label MEASURED / ESTIMATE / VERIFY. Say what you have not checked. When you are wrong, say so plainly and correct it (this session had to correct a disk-space estimate that mixed GB and GiB).
- Never tell Jarvis or Simon to pkill/killall anything; stop services with systemctl or a confirmed PID. Never restart/recreate the open-webui container or edit the production llama-server unit without a backup and a test on a spare port. State plainly anything that could cut Simon off from Jarvis.
- Changes to the box are Simon's decisions. Recommend; don't assume. Nothing gets deleted without his yes.
- Never do Simon's graded schoolwork (his rule).
- No model identifiers in commits or files.
- Jarvis's read_file tool returns only the LAST 4,000 characters of a file (`content[-4000:]`), and run_host_command caps stdout/stderr at 4,000 chars each. Anything long Jarvis must read has to be split into chunks under 4,000 chars or read with `sed -n` ranges.

## Repo map (this branch)
- `docs/jarvis-briefing-2026-09-25.md` (Parts 1-3), `-part4.md` (Simon's 24 wants, hard boundaries, self-improvement plan), `-part5.md` (facts verified on the box; wins on conflicts; updated this session with hardware identity and the model drive).
- `docs/wiki/`: 34 Cowork memory pages copied verbatim (index in README.md). Deep research on every model, lever and plan. `v100-hardware-and-models.md` = the Cowork page "local-model-landscape".
- `docs/benchmark-campaign.md`: the plan to benchmark every model, the per-model "card", model list, phases.
- `docs/glm-5.3-test-plan.md`: GLM-5.3 full test matrix (A stock CPU / B needs Jarvis off / C forks and engines / D downloads / ruled out), with sources.
- `docs/benchmarks/glm-5.3.md`: GLM-5.3 night-1 MEASURED results and analysis.
- `docs/bench/`: sources of the scripts on the box (bench.sh, queue-runner.sh, queue.txt, summary.py, report.sh).
- `docs/jarvis-survey.sh`: read-only box survey (Simon has ~/jarvis-survey.sh).

## The box (jarvis-1)
- Hardware SETTLED by dmidecode: **HYVE G2GPU12**, board ASUS **Z10PG-D16 Series**, BIOS 3803. The ASUS ESC4000 G3 is a SEPARATE machine being set up as a NAS. Chassis facts in the wiki written for "ESC4000" (PSU, GPU harness, max 4 GPUs, ASUS CPU list) do not apply to jarvis-1.
- 2x Xeon E5-2699 v3 (Haswell, AVX2, no AVX-512; 18 cores per socket), 503 GiB RAM (~251 GiB per NUMA node), 2x Tesla V100-PCIE-16GB (both on NUMA node 0), Ubuntu 24.04, driver 580.178.04 (NOT held by apt), CUDA toolkit 12.9 (must stay <=12.9 for sm_70), ECC off, power limit 200 W, numa_balancing 0, governor performance, THP madvise.
- Disks: Samsung 990 PRO 1 TB NVMe (`/`, ext4), SATA optical drive, ~9 free SATA ports. A 4 TB Seagate SkyHawk in a USB enclosure ("model drive", below).
- Memory bandwidth MEASURED (STREAM Triad, after the uncore/governor fix): 29.5 GB/s one socket, 59.5 GB/s both sockets interleaved.
- Production llama-server ExecStart (MEASURED): `numactl --cpunodebind=0 --membind=0 llama-server -hf ggml-org/Qwen3.8-27B-GGUF:Q4_K_M -ngl 99 -sm layer -ts 28,36 -ctk f16 -ctv f16 -c 24576 --host 0.0.0.0 --port 8080 --jinja --chat-template-kwargs '{"reasoning_effort":"xhigh"}' --no-mmproj --no-reasoning-preserve --spec-type draft-mtp -md /home/simon/models/mtp-Qwen3.8-27B-Q4_0.gguf --spec-draft-n-max 5 -devd CUDA0 -ngld 99 --parallel 2 --kv-unified --spec-draft-p-min 0.4`, Restart=always. VRAM ~14.1/14.2 GiB idle, ~15.6 peak under load. Weights come from ~/.cache/huggingface (keep it).
- Context: 4 silent truncations (`truncated = 1`) in 48 h, all slot 0 at n_tokens 24575, i.e. one conversation filling the whole window. A bigger -c is not safe on the GPUs. ~/ctxwatch.py exists (pass 24576 as argv[1]).
- Tool server output caps are live (4000 chars). Tool server still binds 0.0.0.0:8200 (LAN-exposed shell; fix --host 172.17.0.1 is Simon's decision, not done).
- Pre-rebuild stack is gone (job API/worker/ntfy/healthcheck/supervisor/embedding/ACT servers). ~/.ntfy-topic probably does not exist, so runner notifications only go to the log.
- Open WebUI system prompt is only 367 chars; safety sections 13/14/19 missing (Simon to add; not done).

## llama.cpp build facts (~/llama.cpp, f4e276a20, 2026-09-21)
- `--no-mmap` is GONE (error: invalid argument). Use `-lm/--load-mode auto|none|mmap|mlock|mmap+mlock|dio`; also `-lzm/--lazy-mode on|auto|off`. We use `-lm dio -lzm off` (direct I/O into RAM, bypasses page cache).
- No `--mtp` flag. MTP = `--spec-type draft-mtp` (types include draft-simple, draft-eagle3, draft-mtp, draft-dflash, draft-dspark, ngram-*). Whether draft-mtp with no -md uses a head embedded in the model file is VERIFY (GLM-5.3 has one).
- llama-server has -cmoe, -ncmoe, -tb, --cache-reuse, --slot-save-path. llama-bench has -d, -lm, -lzm, -ncmoe, -fitt/-fitc (auto-fit to VRAM), -nkvo, -ot, -o jsonl, but NO -cmoe, NO --threads-batch, no speculative decoding, no --parallel.
- Supports archs qwen4exp (Flash-Next), glm-dsa (GLM-5.3), hy_v4, mimo2, deepseek4; NOT glm5next (GLM-5.3-Flash needs Unsloth's llama.cpp fork).
- On CPU it repacks Q4_K expert weights to q4_K_8x8 at load (stock already does AVX2 repacking).

## Model drive (4 TB, USB, NTFS "Models", /dev/sda2)
- Mounted READ-ONLY at /mnt/models (not in fstab: a reboot unmounts it). Content in /mnt/models/models/ (2.7 TB used). Download chain was stopped deliberately (STOP-CHAIN.txt), no errors.
- LLMs: GLM-5.3 UD-Q4_K_XL (11 shards, 468 GB, MTP head present: blk.78.nextn.* in shard 11), GLM-5.3-Flash UD-Q4_K_XL (6 shards ~200 GB, + mmproj), Qwen3.8-Flash-Next unsloth UD-Q4_K_XL (4 shards ~111 GB) + MTP/ (6 draft variants) + mmproj, Flash-Next GSQ-RCO IQ3_XXS (75.8 GB) and Q2_0 (66.4 GB), MiMo-V2.6-Pro MXFP4 as two RAW parts .part1/.part2 (need `cat` join, ~557 GB) + DFlash draft, HauhauCS 27B Uncensored (IQ4_XS, Q5_K_P, FastMTP draft), Qwen3.8-27B-MTP (Jackrong Q3_K_M 13.5 GB, Q4_K_M 16.8 GB), Qwen3-Coder-Next UD-Q3_K_XL 36.3 GB, Qwen3-VL-32B + mmproj, gpt-oss-20b MXFP4 + eagle3 draft, small models in slots/, embed/, verify/ (router 1.7B, 2B distill, embeddinggemma, rerankers, Qwen3-Embedding-4B, jina-code, OCR, ASR, Qwen3Guard-4B, phi3.5 hallucination judge, Qwen3-VL-4B). Plus audio (audio.cpp GGUFs), video (Wan2.2, LTX-2.5, Hunyuan1.5, SeedVR2), image (Z-Image), corpus, data, train, wheels: these need their own runtimes, not llama.cpp.
- The drive also holds the Cowork session's JARVIS-BRIEFING.md, MANIFEST.md, BUILD-QUEUE.md (Tasks 0-9, Task 0 = backup), RESEARCH-SPEC.md, HANDOFF-PROMPT.txt. Only BUILD-QUEUE task headings and HANDOFF-PROMPT have been read. HANDOFF-PROMPT has wrong paths (/mnt/models/X instead of /mnt/models/models/X): do not give it to Jarvis as-is.
- hf_token.txt (plain-text HF token) is on the drive and readable by any user/Jarvis. Recommended revoking it; Simon has not confirmed.
- Verification: ~/model-verify/ = copy of verify.py pointed at the drive, log on NVMe. Size check passed 53/53. Full sha256 was stopped partway; only 12 files cached. ~/model-verify-nvme/ = copy pointed at /home/simon/models (ROOT) with its own _logs. verify.py only knows 9 repo folders (HauhauCS, Flash-Next unsloth/Q8_0, gpt-oss-20b, both GSQ-RCO, GLM-5.3-Flash, GLM-5.3, MiMo); other folders need a second pass.

## NVMe model copies (/home/simon/models)
- GLM-5.3/ (437 GiB = 468 GB): copied and sha256-VERIFIED (12 files, 05:39Z).
- Qwen3.8-Flash-Next-unsloth/ (128 GiB): copied (fn-copy unit, finished 13:48Z; unit still exists as active(exited) until `sudo systemctl stop fn-copy`, which was done). NOT yet hashed.
- GLM-5.3-Flash/ (188 GiB): copy DONE (glmf-copy, rsync -a, active (exited) ~14:19Z, unit stopped by Simon). MEASURED: file names and byte sizes match the drive exactly, no rsync temp files left. NOT yet hashed.
- mtp-Qwen3.8-27B-Q4_0.gguf (Jarvis's draft, production, keep).
- Space: df showed 250G avail before the GLM-5.3-Flash copy -> ~62G avail after, plus ~46 GiB ext4 root reserve. Base system use ~55 GiB (HF cache 20G is Jarvis's model: keep; docker image 7.2 GB is Open WebUI in use: keep). Optional trim: Flash-Next BF16/Q4 MTP draft files (~16 GiB; keep the two Q8_0 drafts). MiMo join (~557 GB) will NOT fit alongside these; needs a second drive (free SATA ports) or rotating models out.
- RAM rule: Jarvis + ONE big model at a time. GLM-5.3 ~430 GiB resident, Flash-Next ~104 GiB, GLM-5.3-Flash ~186 GiB.

## Simon's goals, in his order
1. FIRST ORDER OF BUSINESS: benchmark every model fully (true max speed, max context, best config, including community forks, other engines, "absolutely everything"), then decide orchestrator slots. Plan: docs/benchmark-campaign.md.
2. Then the model orchestrator (BUILD-QUEUE tasks 0-9: backup, jarvis.db, job queue + worker, ntfy, scheduler, single-card 27B A/B, freed card, router, research pipeline, control room). He wants Jarvis ALWAYS ON: a systemd worker that pulls tasks from SQLite, short fresh model calls per step, grounded checks, ntfy; later a self-improvement loop with a scorer Jarvis cannot write to (Part 4). Claude's recommendation given: backup + db + worker + kill switch/fences/budgets before any unattended or self-improving runs; long-context always-on worker should use Flash-Next on CPU (port 8081), not the 27B on 8080.
3. Backup (WANT 19, his #1 priority on paper): no off-box backup exists. Options offered: restic on the model drive now, NAS later (recommended); undecided.

## Benchmark tooling on the box (sources in docs/bench/, checksums verified)
- ~/bench/bench.sh (41 lines, 5079788b7b862c1e): one-off llama-bench run as unit bench-<label>. Profiles: cpu1 (socket 1 only), cpu (--preferred=1, beside Jarvis), cpuil (--interleave=all, needs Jarvis stopped), gpu (GPUs visible, interleaved, needs Jarvis stopped). CPU profiles hide GPUs (CUDA_VISIBLE_DEVICES=). MemoryMax 465G, no swap, OOMScoreAdjust 1000.
- ~/bench/queue-runner.sh (125 lines, 45f8e6ad3f31cb49): runs ~/bench/queue.txt jobs sequentially as units bench-<label> (systemd-run --wait). Lines: `<label> <profile> <max-hours> <llama-bench args>`. Jarvis-off jobs (cpuil/gpu) only 1-7 AM America/Chicago, max 300 min per night; runner always restarts llama-server and health-checks it (curl :8080/health), retries once, logs NOTIFY. Remembers ~/bench/queue.done and queue.failed (a label in either is skipped: delete the line to re-run). Pause: `touch ~/bench/STOP` (remove it before the next run). Start: `sudo systemd-run --unit=bench-queue --collect -p TimeoutStopSec=900 /home/simon/bench/queue-runner.sh`. Refuses to start while glm-copy/glm-verify/glm-test units are active (does not check fn-copy, glmf-copy, big-verify).
- ~/bench/queue.txt (13 lines, 9b710b677bda2da4): night-1 GLM-5.3 queue.
- ~/bench/summary.py (33 lines, 4b73432e94b907b0): table of a test's jsonl; columns = settings that vary.
- ~/bench/report.sh (29 lines, 05a4225e5c7fe877): `~/bench/report.sh glm` writes ~/bench/report-<time>.txt (system state, queue log, per-test tables, log highlights) for Simon to paste.
- Results: ~/bench/results/<label>/<time>.jsonl + .log + .args. Queue log: ~/bench/queue.log.
- ~/glm-test.sh (28 lines, c06c887620c19c8f): llama-server test unit glm-test on 172.17.0.1:8082 for GLM-5.3 (NVMe path, -lm dio, -c arg default 32768, GPUs hidden, MemoryMax 465G, OOMScoreAdjust 1000). Never run it at the same time as a GLM benchmark (RAM).
- ~/flashnext-test.sh was offered (nohup-based, port 8081, socket 1, points at the DRIVE path and uses --no-mmap, which no longer exists): it is OUTDATED; rewrite as a systemd unit with -lm dio and the NVMe path before use. May not even be saved on the box.

## Night 1 (GLM-5.3) results, MEASURED (full write-up: docs/benchmarks/glm-5.3.md)
- Decode: 0.9-1.1 t/s beside Jarvis; **1.48 t/s interleaved with Jarvis off** (~37 GB/s effective, ~62% of STREAM). At 16K depth: 0.74 (beside) / 1.00 (interleaved).
- Prefill: ~10 t/s (pp512), ~7.6 t/s (pp4096) at empty context; ~2.5-2.8 t/s at 16K depth, ~4-4.7 at 8K. Prefill at depth is the real wall (full MLA attention, no DSA sparse indexer in llama.cpp).
- No effect: ubatch 512-4096 (<4%), 72 vs 36 threads for prefill (+1%), threads for decode. FA on: +17% decode at 8K, -15% prefill at 8K.
- Failures (test design errors): `-cmoe` does not exist in llama-bench; `-ncmoe 76/74` -> "unable to allocate CUDA1 buffer"; `-ctk q8_0 -fa on` -> "failed to create context" (retry with -fa off).
- Resident: CPU 184,022 MiB + CPU_REPACK 255,744 MiB. KV bytes/token NOT yet measured (llama-bench does not print it; use a llama-server run).
- Night-1 queue status at 14:06Z: done a1-threads, b1-interleave, b1-smt-prefill, a2-batch, a3-fa; failed b2-hybrid-cmoe, b2-hybrid-ncmoe76, b2-hybrid-ncmoe74, a5-kcache; **a6-depth RUNNING since 13:31Z (cap 4 h, until 17:31Z)**, a7-poll after it (~30 min). Jarvis back up and healthy since 09:27Z.

## Session 2026-09-25 afternoon (updates on top of the above)
- glmf-copy DONE and stopped; GLM-5.3-Flash copy matches the drive by names and byte sizes.
- a6-depth partial: d0 1.106, d4096 0.928 t/s. d16384 expected ~15:05-15:10Z. d32768 cannot finish before the 17:31Z cap: recommended stopping bench-glm-a6-depth after the 16K line (Simon's call, not yet confirmed).
- Flash-Next day-1 queue written: docs/bench/queue-fn.txt (15 lines, 2688 B, f6751ff9b097e02c), to be saved as ~/bench/queue-fn.txt. Simon has NOT yet confirmed pasting it. Swap into queue.txt only after the GLM queue finishes and big-verify is done (save the old one as queue-glm-night1.txt). Never edit queue.txt or queue-runner.sh while the runner is running.
- Flash-Next MTP: stock build has no qwen4exp MTP (MEASURED by grep). PR #28243 fetched as a worktree at ~/llama.cpp-fnmtp, commit 6fcaa16f4, base bb3c853c3 (5 commits behind production). Not built yet; build command (unit build-fnmtp, CPU-only) is at the end of docs/benchmarks/qwen3.8-flash-next.md; run it only after the GLM queue finishes. Use shared-Q8_0 MTP head, -md explicit, n-max 2 default; always check greedy output identical with MTP off.
- Corrected Flash-Next speed estimate: ~5-6 t/s socket 1, ~10 interleaved, ~13-19 best case with mirror + MTP. The wiki's 18-27 was a stacked best case. docs/benchmarks/qwen3.8-flash-next.md.
- GLM-5.3 1M context: not practical (see docs/benchmarks/glm-5.3.md).
- GSQ-RCO file names still needed: ls the IQ3_XXS/ and Q2_0/ subfolders on the drive.
- MTP test harness WRITTEN: docs/bench/mtp-test.py (109 lines, 5894 B, 3dfaa4e2f38ae95e) -> ~/bench/mtp-test.py; 7 configs (off, shared-Q8 n-max 1-4, shared-Q4 n2, full-Q8 n2) x 3 prompts, temp 0, checks output IDENTICAL to MTP off. Run only after the Flash-Next queue finishes (it refuses while bench-queue is active). draft_n/draft_n_accepted timing keys are VERIFY (fallback: "draft acceptance" line in the server logs). The general llama-server harness (parallel, cache reuse, slot save, needle) is still not written.
- GLM night-1 queue FINISHED 10:28 AM CT (7 done, 4 failed). a6: 1.11 / 0.93 / 0.74 t/s at depth 0 / 4K / 16K; a7 poll: no effect. Jarvis healthy, 489 GiB RAM available afterwards (12:13 PM CT). Box login banner: 54 apt updates pending, swap 5% used, / 88.2% used. big-verify DONE 12:33 PM CT: Flash-Next + GLM-5.3-Flash, 21 files, 338.8 GB, ALL MATCH. build-fnmtp DONE 12:16 PM CT. ~/bench/queue-fn.txt saved and checksum-verified (f6751ff9b097e02c). Next: stop big-verify unit, save queue.txt as queue-glm-night1.txt, copy queue-fn.txt to queue.txt, start runner. NOTE: the runner exits after the daytime cpu1 jobs if outside 1-7 AM; the two cpuil jobs need a restart in the night window.

- Simon's full orchestrator wants received 2026-09-25: docs/orchestrator-wants-simon-2026-09-25.md (+ .docx). Role tests derived from them added to docs/benchmark-campaign.md.

- Simon approved (2026-09-25): (1) interleave-beside-Jarvis test, docs/bench/il-beside.py -> ~/bench/il-beside.py (98 lines, 4946 B, 95e32f924b835a10), auto-stops if Jarvis < 75% of baseline twice; run after mtp-test. (2) ik_llama.cpp CLONED ~/ik_llama.cpp at 1aaf7105 (2026-09-25): qwen4exp supported (grep). Build after the Flash-Next queue. il-beside.py saved and checksum-confirmed. ik: fused MoE default on, -fdn fused delta-net exists, qwen4exp NextN companion-file support, no NUMA mirror option.
- Flash-Next day-1 sweep MEASURED (see docs/benchmarks/qwen3.8-flash-next.md): decode best at 9 threads (4.38), prefill best at 36 (31.67); ub 512 best; fa ~neutral; q8_0 cache free; 64K depth decode 2.91, prefill 10.66. Harness tweaks after it: il-beside.py threads -> 12,18,24,36 (98 lines, 4952 B, cfd7d818bcc8da46); mtp-test.py -> -t 12 -tb 36 (109 lines, 5907 B, 3e55580b5ff38e57), applied on the box with sed.
- Flash-Next day-1 queue FINISHED 4:33 PM CT (poll no effect; end control 4.19 t/s, stable). Harness sed updates applied and checksums confirmed on the box. mtp-test DONE 5:19 PM CT: best shared-Q8 n-max 3 = 1.57x mean (6.73 t/s), all MTP configs identical to each other, differ from off at a near-tie token. il-beside DONE 5:35 PM CT: interleaved beside Jarvis decode 5.60 t/s (18 thr), prefill 50.66 (36 thr); Jarvis median -3%, worst -15%. Next: build-ik, then ik head-to-head; then MTP + interleave together. Also owed: MTP-off run-to-run identity check; shared-Q4 at n-max 3.
- Master speed-lever list: docs/speed-levers.md (Simon: "speed up in ANY and EVERY possible way").

## Next steps, in order
1. DONE ~14:20Z: glmf-copy finished (188G, names+sizes match the drive) and was stopped.
2. When `tail -3 ~/bench/queue.log` shows "Benchmark queue finished" (not before: hashing and building distort running benchmarks): hash both new copies:
   `sudo systemd-run --unit=big-verify -p User=simon -p Group=simon -p Nice=10 -p RemainAfterExit=yes -p WorkingDirectory=/home/simon/model-verify-nvme /usr/bin/python3 /home/simon/model-verify-nvme/verify.py --only Qwen3.8-Flash-Next-unsloth GLM-5.3-Flash` (~18 min; watch `journalctl -u big-verify`; then `sudo systemctl stop big-verify`).
3. Build ik_llama.cpp CPU-only in ~/ik_llama.cpp (commands were given: clone, cmake -DGGML_CUDA=OFF -DGGML_NATIVE=ON, build llama-bench llama-server llama-sweep-bench, then grep src for glm-dsa and list its -fmoe/-mla/-rtr/-amb/-ser flags). Not done yet.
4. Analyse a6-depth and a7-poll results (`~/bench/report.sh glm`), update docs/benchmarks/glm-5.3.md.
5. Night-2 queue for GLM-5.3: baseline control each night; interleave + fa on/off; depth curve interleaved; hybrid done right (-ngl 99 -ncmoe 79 = all experts on CPU, then llama-bench -fitt auto-fit, or walk -ncmoe down one layer at a time); -ctk q8_0 with -fa off; ik_llama.cpp head-to-head (-rtr, -fmoe, -mla modes, -amb, --split-mode graph, llama-sweep-bench). Remove or relabel the failed labels in queue.failed/queue.txt so they re-run.
6. Server-mode tests need a new llama-server test harness (not written yet): KV bytes/token from the startup log, MTP (--spec-type draft-mtp, n-max 1-5, p-min 0/0.4), --parallel 1/2/4/8 aggregate t/s, --cache-reuse 256 with -lv 4, --slot-save-path save/restore, needle test at max -c with truncated = 0. Add a server mode to the queue runner.
7. Then Flash-Next family (UD-Q4_K_XL + MTP drafts, GSQ-RCO IQ3_XXS and Q2_0; fits one socket so NUMA mirroring forks are testable), GLM-5.3-Flash (needs Unsloth fork build), GPU models in Jarvis-off windows (27B baseline, 27B-MTP Q3/Q4 single-card A/B, HauhauCS, VL-32B, gpt-oss-20b, Coder-Next), small models, MiMo last (needs join space and the whole box).
8. Community/fork candidates found (details and links in docs/glm-5.3-test-plan.md section C and RULED OUT): ik_llama.cpp; llama.cpp PR #27861 GPU LRU expert cache; JigSawPT/moe-autopilot; discussion #24528; DSA indexer work (PR #21149 / discussion #21183, fairydreaming deepseek-dsa branch, ubergarm GLM-5.1 draft); KTransformers (AVX2 backend since Mar 2026; GLM-5.3 full and Volta support VERIFY); llama.cpp-ng; PrismML PR #251; TurboQuant CPU forks. NUMA mirror (PR #27986, ik PR #2396) impossible for GLM-5.3 at Q4 (870 GiB), fine for Flash-Next. PR #25294 (stream experts from disk) is for MiMo.

## Still pending from earlier (unconfirmed or undecided)
- Jackrong-wording fix to ~/jarvis-memory/briefing-2026-09-25.md (was 26,612 B / 230ee4de59c4058d; fix script /tmp/fix-jackrong.py hash 2cb672e4e2d1a818 should give 26,764 B / 794606f5864d29df) and saving Part 5 (48 lines, 6,079 B, 1e5775436aea51a0) + a state.md pointer line: blocks were given, Simon never confirmed running them. Part 4 on the box matches the repo (7dd4fa07d462a1e5).
- Jarvis's state.md is stale (Sep 21 config, calls Simon "Jack").
- Driver hold, HF token revoke, tool-server bind fix, system-prompt safety block, ECC: all Simon's decisions, not done.
- Read the drive's BUILD-QUEUE.md, RESEARCH-SPEC.md, JARVIS-BRIEFING.md, MANIFEST.md in full (Simon to cat them); then write orchestrator-plan.md reconciled with the box, plus a chunked (<4000 chars per part) version for Jarvis.
- Missing Cowork pages Simon may transfer (model-pull-and-flags, model-storage-plan, local-ai-setup, jarvis-backup, nvme-drive-failure, quant-quality-tables, model-tier-ceiling, glm-5.3-download, fast-house-extras, learning-partner, esc4000-parts-order). Save verbatim into docs/wiki/ with the header convention and update docs/wiki/README.md.
- /etc/fstab entry for the model drive (read-only) not created.
