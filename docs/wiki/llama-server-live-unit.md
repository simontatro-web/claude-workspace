# llama-server-live-unit

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 23, 2026).
> Cowork-only links kept as page names.
>
> Summary: The LIVE llama-server.service unit on jarvis-1 as audited Sep 23 2026 — the exact running flags, which are deliberate and measured (do not "fix" them), what is genuinely still open, and the retraction of a bad audit. Read BEFORE proposing any change to the running 27B server.

Companion: jarvis-speed-tuning holds all the measurements behind these flags and hit its size cap, which is why this file exists. jarvis-incidents holds the pkill history.

## THE LIVE ExecStart, read from ps Sep 23 2026 (PID 73808, up since Sep 22)

```bash
/home/simon/llama.cpp/build/bin/llama-server \
  -hf ggml-org/Qwen3.8-27B-GGUF:Q4_K_M -ngl 99 -sm layer -ts 28,36 \
  -ctk f16 -ctv f16 -c 24576 --host 0.0.0.0 --port 8080 --jinja \
  --no-mmproj --no-reasoning-preserve \
  --spec-type draft-mtp -md /home/simon/models/mtp-Qwen3.8-27B-Q4_0.gguf \
  --spec-draft-n-max 5 -devd CUDA0 -ngld 99 --parallel 2 --kv-unified
```

Build: 0.4.1-dev, build 11089, commit f4e276a20, GNU 13.3.0. Managed by llama-server.service (systemd). Restart through the unit. NEVER pkill — that has killed production on this box more than once.

## *** RETRACTION: I AUDITED THIS UNIT WITHOUT READING jarvis-speed-tuning FIRST AND CALLED THREE MEASURED SETTINGS "GAPS". ALL THREE WERE WRONG. ***

| I claimed | Reality, already measured on this box | | "-ctk f16 -ctv f16 wastes VRAM, switch to q8_0" | BACKWARDS. q8_0 KV dequant WAS the entire 49% decay. f16 gave +69.3% long-gen, +48.9% copy-heavy, +61% prefill, and flattened decay from -48.3% to -0.6%. Biggest win ever measured here. NEVER recommend q8_0 KV on this box again. | | "--spec-draft-n-max 5 is too low, raise to 15" | STRICTLY WORSE, swept twice. Past 5, acceptance collapses 0.385 -> 0.246 while mean accepted draft length barely moves. n=8 costs 33% on predictable work. Monotonic loss past 5. | | "-ts 28,36 compensates for the CLIP workspace, retest even" | NO. Deliberate VRAM balance that let f16 KV fit without OOM (GPU0 14,098 / GPU1 14,396). An even split flips the imbalance toward the 622 MiB-free state that core-dumped Sep 22 00:05. | ROOT CAUSE: I applied the generic cross-model flag list to a box whose per-flag behaviour is empirically tuned and written down. *** THE GENERIC LISTS IN system-performance-levers AND model-pull-and-flags GOVERN THE UNBUILT CPU MODELS. THEY DO NOT GOVERN THIS UNIT. *** Also corrected: -fa defaults to auto on build 11089 (--help: "set Flash Attention use ('on','off','auto'), default: 'auto'"), so it is not "missing from the command line". jarvis-speed-tuning already demoted FA to a prefill/VRAM candidate once f16 KV explained the whole decay.

## WHAT IS GENUINELY STILL OPEN

- reasoning_effort IS absent from the ExecStart. system-performance-levers rates --chat-template-kwargs '{"reasoning_effort":"xhigh"}' at 8 AA index points (34 vs 26) for zero cost. Highest-value open item on the unit.
- LIVE MISMATCH RISK: the unit runs -c 24576 (the recommended drop from 32768 was applied). jarvis-speed-tuning records that Open WebUI's jarvis row carries num_ctx: 32768 in params and that if -c drops, num_ctx MUST drop to match or the UI requests a window the server does not have. CHECK AND FIX.
- -b 4096 survives as a candidate but is NOT free here. Untested. Raising -b grows compute buffers, and live-load VRAM is GPU0 15,620 / GPU1 15,166, only ~728 MiB free vs the 622 MiB that crashed. Test on a spare port with the service stopped, never by editing the production unit.
- Model weights are not in ~/models RESOLVED Sep 23 2026. The -hf cache is ~/.cache/huggingface/hub/, NOT ~/.cache/llama.cpp/ (that path genuinely does not exist on this box — correcting the earlier note). Canonical model path: /home/simon/.cache/huggingface/hub/models--ggml-org--Qwen3.8-27B-GGUF/snapshots/efbb3b1f70a21d97fd4495240648405f7228554f/Qwen3.8-27B-Q4_K_M.gguf (blob behind it: .../blobs/c600de0300ae8a0eb3a6c0b8b5561b8b96f16bd2c863c2a66c42de29d391a747.) METHOD THAT WORKED: sudo ls -l /proc/\<pid>/fd | grep gguf returned NOTHING — llama.cpp closes the fd after mmap. Use sudo grep -i gguf /proc/\<pid>/maps | awk '{print $6}' | sort -u instead; that also confirms the MTP head at /home/simon/models/mtp-Qwen3.8-27B-Q4_0.gguf. Get the live PID with systemctl show -p MainPID --value llama-server.service. BENCH METHODOLOGY NOTE for the -ngl 0 calibration: warm the page cache first (cat "$MODEL" > /dev/null). -ngl 0 mmaps the weights, so a cold first rep reads 17.66 GiB off NVMe and measures the DRIVE, not memory bandwidth — it would silently under-report and corrupt the back-solve. Also use -r 3 (not the default 5) and run it with nobody using the chat, since 36 threads saturate both memory controllers.
- ~/models/GLM-5.3-GGUF still holds 50 GB of dead .incomplete files. Disk: 915G total, 104G used, 766G free.

## GPU FACTS CONFIRMED Sep 23 2026

Both Tesla V100-PCIE-16GB at Gen3 x16 current and max (no riser/bifurcation problem), persistence mode Enabled, ECC Enabled on both. nvidia-smi topo -m: PHB, both cards on NUMA node 0, CPU affinity 0-17,36-53. *** Because both GPUs hang off socket 0, GPU and hybrid slots should pin CPU threads to node 0. This CONFLICTS with the interleave-everything rule for pure-CPU models — the right answer is per slot. *** ECC off would free ~1 GiB usable VRAM per card (~2 GiB total) plus a few percent bandwidth (sudo nvidia-smi -e 0, needs reboot). Directly relevant to item 3 above, where the blocker is ~728 MiB of headroom. Tradeoff: no single-bit correction on used Teslas; for inference that is a wrong token, not a crash.

## *** Sep 23 2026 (later session) — xhigh APPLIED AND VERIFIED. ECC ITEM CLOSED AS A DEAD END. BOOT BUG FOUND. [MEASURED] ***

THE LIVE ExecStart ALREADY CARRIED A FLAG THIS FILE DID NOT RECORD: --spec-draft-p-min 0.4. Read from /etc/systemd/system/llama-server.service Sep 23. The ExecStart transcribed at the top of this file (from ps) omits it, so that transcription is stale. Left untouched — same measured-and-tuned category as the rest. Do not "fix" it.

ITEM 1 (reasoning_effort) DONE AND PROVEN. Added --chat-template-kwargs '{"reasoning_effort":"xhigh"}' after --jinja. systemd passes it correctly as one argument (visible in the CGroup line as "{\"reasoning_effort\":\"xhigh\"}"). Backup of the pre-change unit: /etc/systemd/system/llama-server.service.pre-xhigh. PROOF THE KWARG IS ACTUALLY CONSUMED, not silently ignored — per-request A/B via chat_template_kwargs in the request body (works on b11089, no restart needed), same hard prompt, temperature 0: | reasoning_effort | reasoning_content chars | | low | 2,770 | | medium | 7,405 | | xhigh | 9,193 | Monotonic, so the flag is real and live. *** CORRECTION: xhigh IS NOT "ZERO COST". *** Zero cost in THROUGHPUT (t/s unchanged) but ~3.3x the reasoning tokens of low, i.e. roughly 45 s of thinking before the answer vs ~13 s, at ~51 t/s. Keep it for hard work; override per request with chat_template_kwargs in the body when a fast answer matters. Read system-performance-levers's "8 AA index points, costs nothing" with this caveat.

### *** ITEM 3 (-b 4096) IS DEAD, NOT DEFERRED. ECC OFF FREES EXACTLY ZERO VRAM ON V100. [MEASURED] ***

```bash
sudo nvidia-smi -e 0 applied, rebooted, ECC confirmed Disabled on both cards. | | ECC Enabled | ECC Disabled | | nvidia-smi memory.total | 16,384 MiB | 16,384 MiB | | llama-server --list-devices usable | 16,144 MiB | 16,144 MiB | Usable VRAM did not move one megabyte. V100 HBM2 uses dedicated ECC storage rather than carving capacity out of the user-visible pool. The "~1 GiB per card" figure in the GPU FACTS section above is WRONG, and so was a 240 MiB revision guessed from the 16384/16144 gap — that gap is ordinary reservation, unrelated to ECC. CONSEQUENCE: -b 4096 loses its entire premise. No new headroom, GPU0 still peaks near 728 MiB free under real load, and the 622 MiB crash of Sep 22 00:05 still bounds it. Do not test -b 4096 on this configuration. The only remaining route to more prefill AND more context is the fishlikeX/sm70-attn flash-attention fork (+39.9% prefill measured, unlocks quantized V-cache = 2-4x context). ECC IS NOW OFF FOR NO BENEFIT. Recommend sudo nvidia-smi -e 1 + reboot at the next convenient reboot unless the fork work needs it off — currently carrying single-bit-error risk on used Teslas for zero return.
```

### *** BOOT BUG, PRE-EXISTING AND SILENT: llama-server NEVER STARTS ON REBOOT. FIXED. [MEASURED] ***

After the ECC reboot, llama-server.service was inactive (dead) with zero journal entries — never attempted, not crashed. Root cause, verbatim from journalctl -b:

multi-user.target: Found ordering cycle on llama-server.service/start

multi-user.target: Found dependency on nvidia-powercap.service/start

multi-user.target: Found dependency on multi-user.target/start

Job llama-server.service/start deleted to break ordering cycle starting with multi-user.target/start

CAUSE: nvidia-powercap.service was both WantedBy=multi-user.target AND After=multi-user.target — a dependency cycle. systemd breaks cycles by deleting a job, and llama-server.service (ordered After=nvidia-powercap.service) is what got deleted. THIS PREDATES the xhigh edit. The box had not rebooted since Sep 21, so every reboot of this machine has silently left Jarvis down until someone started it by hand. SIGNATURE TO RECOGNISE: unit enabled, symlink present in multi-user.target.wants/, inactive (dead), and NO log entries at all. No entries means no start attempt, which is never a crash — do not go hunting for a bad flag. FIX APPLIED: sudo systemctl disable --now nvidia-powercap.service. Verified across a subsequent reboot: llama-server.service came up active unaided and the cycle lines are gone. gpu-tune.service is now the single owner of persistence mode and the power limit (clean ordering: After=nvidia-persistenced.service, Before=llama-server.service).

### POWER LIMIT: 250W vs 200W IS NOISE. SETTLED, STOP REVISITING. [MEASURED]

Two units were fighting over it (gpu-tune set 250, nvidia-powercap set 200, nondeterministic winner). After consolidating, measured six alternating runs, first discarded: | | short t/s | copy-heavy t/s | | 250 W | 51.26 / 51.14 / 51.17 | 65.71 / 65.63 / 65.68 | | 200 W | 51.30 / 51.15 / 51.22 | 65.67 / 65.61 / 65.63 | Under 0.2% spread and the settings interleave. 50 extra watts per card buys nothing. gpu-tune.service set back to -pl 200 so the boot config matches the measurement. Confirms this file's existing power-curve conclusion; do not spend effort here again.

### BENCH SCRIPT REBUILT AT ~/bench.py — BUT IT IS NOT THE ORIGINAL METHODOLOGY

/tmp/bench.py was lost again (reboot; /tmp does not survive on this box). Rebuilt at /home/simon/bench.py, run python3 ~/bench.py \<port>. *** ITS NUMBERS ARE NOT COMPARABLE TO ANY FIGURE EARLIER IN THIS FILE OR IN jarvis-speed-tuning. *** The original copy-heavy test sent a 506-token Python file and generated ~648 tokens; the rebuild sends 289 tokens and generates 422. Steady state on the rebuild is short ~51.2 t/s, copy-heavy ~65.6 t/s — a NEW baseline, NOT a regression from the recorded 61/77. Use it only for A/B within itself. COLD-START GOTCHA CONFIRMED: the first bench run after a service start reads ~6% low (48.12 vs 51.2 steady). Always discard the first run. A 200W-vs-250W comparison was initially misread because of exactly this.

### ITEMS 2 AND 5 CLOSED Sep 23 2026

ITEM 2 (num_ctx mismatch) FIXED. Open WebUI's jarvis row carried num_ctx: 32768 against the server's -c 24576 — a genuine live mismatch, confirmed by reading the row. Set to 24576 via a python read-modify-write on webui.db, then docker restart open-webui; verified by re-reading the row. docker needs sudo on this box (plain docker exec fails with "permission denied ... /var/run/docker.sock"). Backup taken first: /app/backend/data/webui.db.bak-numctx-\<timestamp> inside the container. The rest of the params row is intact and worth knowing: temperature: 0 (the Sep 22 speed fix), function_calling: "native", builtin_tools: False (the Sep 21 6,100-token-tax fix), plus a system prompt instructing Jarvis to use write_file rather than heredocs through run_host_command. Any future edit to this row must preserve all four. ITEM 5 (dead GLM download) DONE. ~/models/GLM-5.3-GGUF/ held 33 .incomplete shards and nothing else — verified with find ... -name '*.gguf' -size +1G returning empty; the only non-.incomplete files were .lock/.metadata bookkeeping under .cache/huggingface/download/. Removed. Disk now 915G total, 54G used, 815G free (was 766G). ALL SIX ITEMS ON THE Sep 23 PRIORITY LIST ARE NOW CLOSED. Three real wins (jarvis-perf unit persisted and reboot-verified, xhigh live and proven, the boot ordering-cycle bug fixed), two dead ends established by measurement (ECC frees zero VRAM so -b 4096 is off the table; 250W vs 200W is noise), one still owed (the clean interleaved llama-bench re-run, see system-performance-levers).

## *** Sep 23 2026 — fishlikeX/sm70-attn FORK BUILT AND BENCHMARKED ON THE BOX. PREFILL WINS BIG, DECODE LOSES BIG. [MEASURED] ***

Built at ~/sm70-attn (separate repo and build tree; production ~/llama.cpp/build/bin/llama-server never touched). Test harness: ~/fa-test.sh "\<extra flags>" runs the fork on port 8099 with production's exact flags plus -fa on, defaults -ctk f16 -ctv f16 -c 24576. Logs ~/fa-run1.log / ~/fa-run2.log / ~/fa-run3.log.

PRE-BUILD CHECKS THAT MATTERED:

- Mainline is NOT an option. llama.cpp PR #28887 "CUDA: enable sparse FlashAttention on Volta" is CLOSED, not merged (Sep 14 2026, closed over an AI-usage-policy violation), and it only supports head_dim 512 for DeepSeek-V4 sparse attention. Qwen3.8-27B has 256-dim heads. No upstream route exists.
- The fork carries MTP — verified by grep before building, this was the go/no-go. common/speculative.cpp:1330 struct common_speculative_impl_draft_mtp, common/common.h:175 COMMON_SPECULATIVE_TYPE_DRAFT_MTP, common/arg.cpp:3083, plus --spec-draft-p-min at arg.cpp:4194. It also has DRAFT_EAGLE3 / DRAFT_DFLASH / DRAFT_DSPARK, i.e. a SUPERSET of b11089. Its baseline-2026-08-18 tag is misleading — HEAD is 707cf247c, Sep 22 2026.
- Configure: cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=70 -DLLAMA_CURL=ON, CUDA 12.9.86, ggml 0.23.0. Key line: FlashAttention K-V type combinations: f16-f16;q4_0-q4_0;q8_0-q8_0;bf16-bf16 — matched PAIRS only. The fork README's own -ctk q4_0 -ctv f16 is MIXED and not compiled; mixed combos need -DGGML_CUDA_FA_ALL_QUANTS=ON (much longer build). Also Could NOT find NCCL, warned as suboptimal for multi-GPU.
- --spec-draft-p-min 0.4 on the live unit traces to llama.cpp discussion #25198 "Pushing MTP to the limit with --spec-draft-p-min (15% faster)". Deliberate, community-measured. Leave it.

THE NUMBERS (same ~/bench.py and same count-to-2500 decay script throughout; old-binary 83.69 figure is from the Sep 22 f16 production run, different script — see the caveat below): | config | decode, 3500-tok gen | prefill | VRAM GPU0/GPU1 | | old binary, f16, no FA | 83.69 | 633-650 t/s (10.5K prompt) | — | | fork +FA, f16, -c 24576 | 63.72 | 905.85 t/s (14,018 tok) | 10,968 / 12,624 | | fork +FA, q8_0, -c 65536 | 59.25 | — | 11,438 / 13,158 | Short/copy-heavy on the fork at f16/24576: 49.78 / 65.01 vs old binary 51.2 / 65.6 — parity, as expected since FA is not a decode lever.

*** FINDING 1: FA LARGELY FIXES THE q8_0 DEQUANT PENALTY. *** q8_0 vs f16 costs only -7% with FA (63.72 -> 59.25). Without FA the same swap cost -41% (83.69 -> 49.4). The mechanism argument held: with FA the KV is read inside the kernel. *** FINDING 2: AND IT DOESN'T MATTER, BECAUSE THE FORK ITSELF COSTS ~24% OF DECODE. *** 63.72 vs 83.69 at identical KV type. That swamps the KV gain entirely. *** FINDING 3: PREFILL IS REAL AND LARGE. 905.85 t/s on 14,018 tokens vs 633-650 recorded, ~+41%, matching the fork's own +39.9% claim. *** CONTEXT IS CHEAP ONCE FA IS PRESENT: q8_0 @ 65,536 cost only ~+470/+534 MiB over f16 @ 24,576. 2.7x the window for ~1 GB, both cards under the 15,300 safety rule with ~3.0 GiB free on the tighter one. 98K-131K looked reachable.

OPEN CAVEAT — THE VERDICT IS NOT FINAL. The 83.69 baseline was measured with a DIFFERENT script, no xhigh, and enable_thinking false, so the -24% is not yet a clean A/B. The owed test is the identical decay script and identical 14K prefill script run against production on port 8080. Do that before concluding anything. PROVISIONAL READ IF THE A/B HOLDS: do NOT ship the fork. The trade is +41% prefill and 2.7x context for -24% decode, and decode is what is felt on every message. Context also already has a cheaper fix in the run_host_command output cap (jarvis-run-host-commands), which cut context growth ~86%. UNTESTED SPLIT THAT COULD SAVE IT: run the fork with -fa off to separate "flash attention costs decode" from "this binary costs decode". If the binary alone is fine, a rebase of the sm70 kernels onto b11089 becomes the interesting path.

OPERATIONAL NOTES FROM THIS RUN:

- [sm70-d256] ph#N REJECT: no mask or small batch appears exactly 20 times at warmup and never again — ph#N is a first-20-calls probe, not continuous logging. Absence of ACCEPT lines does NOT mean the kernel didn't fire; the prefill number is the only evidence. Warmup rejects are correct: the gate is causal-masked prefill at batch >=256 and warmup is a 2-token batch.
- Port collision: run 1's server survives Ctrl-C in another window and holds 8099. Find it with sudo ss -ltnp | grep 8099 and kill \<pid> — targeted PID kill, never pkill llama-server.
- docker needs sudo on this box.
- The -hf model must be given to the fork as the local snapshot path, not -hf, so nothing re-downloads.

FINAL WRITE
