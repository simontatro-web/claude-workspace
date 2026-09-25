# Qwen3.8-27B Q4_K_M (Jarvis, production): speed research and runbook

Written 2026-09-25 (evening, Central time) for Simon. This is an independent pass for this model only.
Labels: **MEASURED** (on jarvis-1, with date), **SOURCE** (link), **ESTIMATE** (arithmetic shown), **VERIFY** (not checked; the command that settles it is in section E).
Scripts: `docs/speed-research/scripts/j27_logstats.py` (77 lines, 3,464 B, sha256 `fb7817288dbaffa2`), `t27_window.py` (390 lines, 22,533 B, `05d965589667b06d`), delivered to the box with `deliver-27b.sh` (476 lines, 26,642 B, `b24fe79be242015f`). Both scripts were tested here against a fake llama-server with stubbed `systemctl`/`systemd-run`/`nvidia-smi`, including stored-reference reuse, missing-file skips and SIGTERM → Jarvis restored. They have not run on the box yet.

## A. Current state

**Production** (llama-server.service, port 8080, MEASURED from the unit, see docs/HANDOFF.md):
`numactl --cpunodebind=0 --membind=0 llama-server -hf ggml-org/Qwen3.8-27B-GGUF:Q4_K_M -ngl 99 -sm layer -ts 28,36 -ctk f16 -ctv f16 -c 24576 --host 0.0.0.0 --port 8080 --jinja --chat-template-kwargs '{"reasoning_effort":"xhigh"}' --no-mmproj --no-reasoning-preserve --spec-type draft-mtp -md /home/simon/models/mtp-Qwen3.8-27B-Q4_0.gguf --spec-draft-n-max 5 -devd CUDA0 -ngld 99 --parallel 2 --kv-unified --spec-draft-p-min 0.4`
Binary: stock llama.cpp f4e276a20 (2026-09-21), CUDA 12.9, sm_70. Open WebUI sends temperature 0 and num_ctx 24576.

**Measured numbers** (all MEASURED on jarvis-1; sources are the wiki pages jarvis-speed-tuning, v100-speed-frontier, llama-server-live-unit, and briefing Part 5):

| Date (CT) | What | Result |
|---|---|---|
| Sep 21 | No speculation, short prompt | 28.08-28.10 t/s decode |
| Sep 21 7:27 PM | f16 KV + MTP n-max 5, 3,500-token generation | 83.69 t/s average, flat (-0.6% start to end); old bench.py short 61.08 / copy-heavy 77.30; prefill 480 t/s on a 506-token prompt |
| Sep 21 evening | n-max re-sweep on f16 | n5 best: reasoning 42.35 t/s (draft acceptance 0.385), predictable 65.48 (0.713); n8-n12 all worse (34-48) |
| Sep 21 8:02-8:27 PM | Real agentic run, 14 turns, 9K-32K context | 29-52 t/s per turn; prefill 633-650 t/s on 2.8K-10.5K prompts; depth costs ~nothing (19.54 vs 19.43 ms/token at 11.9K vs 24.4K) |
| Sep 21-22 | Temperature 0 / 0.3 / 0.8 | 51.08 / 42.25 / 41.15 t/s: temperature 0 is the speed setting |
| Sep 21 ~11 PM | p-min 0 / 0.4 / 0.6 / 0.8 | reasoning 50.81 / 55.93 / 47.04 / 42.65; predictable 59.27 / 56.29 / 61.29 / 55.21 |
| Sep 23 | Current bench.py baseline (new script, not comparable to older rows) | short ~51.2, copy-heavy ~65.6 t/s; 200 W vs 250 W identical |
| Sep 23 | sm70-attn fork with FA (f16, 24576) | prefill 905.85 t/s on 14,018 tokens (+41% vs 633-650); decode 63.72 on the 3,500-token test (vs 83.69 with an older script, so the -24% is not a clean A/B); bench.py 49.78 / 65.01; VRAM 10,968 / 12,624 MiB |
| Sep 24 8 PM | Box survey | VRAM 13,914 / 14,130 MiB idle |
| Sep 23-25 | Context | 4 silent truncations (`truncated = 1`) in 48 h, all at n_tokens 24575 |

**What limits speed (arithmetic):**
- Decode is HBM-bandwidth-bound. Weights = 17.66 GiB = 18.96 GB read per target forward pass. With `-sm layer` the two cards read their halves one after the other, so a pass costs at least 18.96 GB / 900 GB/s = 21.1 ms → ≤ 47 t/s with no speculation at 100% efficiency. The measured 28.1-29.5 t/s is ~60% of that (ESTIMATE from MEASURED numbers). The second V100 adds memory, not speed: a 2× V100 run of this same model measured layer-split decode equal to single-GPU decode ([llama-split-bench](https://github.com/eightman999/llama-split-bench), SOURCE).
- MTP multiplies tokens per pass. At n-max 5 the server's "mean len" (tokens per verify step, the target's own token included) was 2.91 on open reasoning and 4.56 on predictable text (MEASURED Sep 21). Acceptance 0.385 and 0.713 of 5 drafted tokens, plus 1, give the same numbers. That is why real turns land between 29 and 52 t/s depending on content, not depth.
- Prefill is compute-bound (cuBLAS fp16 tensor cores on V100). Flash attention is not active: the log says "Flash Attention not supported, set to disabled". The likely reason is that FA was compiled out. The production commit contains a change that breaks compiling FA for sm_70 ([llama.cpp #29222](https://github.com/ggml-org/llama.cpp/issues/29222), fixed by [PR #29224](https://github.com/ggml-org/llama.cpp/pull/29224) = commit b1c2863 on Sep 21). The wiki records the Sep 21 build as `-DGGML_CUDA_FA=OFF`. I read the current master source: FA kernel selection for head size 256 and f16 KV on Volta returns the tile/MMA kernels, so FA works if it is compiled (SOURCE: `ggml/src/ggml-cuda/fattn.cu`, `ggml_cuda_get_best_fattn_kernel`). VERIFY on the box (E1).
- Context is VRAM-bound: without FA, the attention score buffers grow with `-c`. At `-c 24576` the cards peak at ~15.6 of 16.1 GiB (MEASURED). That is why the window stopped at 24,576 and conversations get truncated.
- No FA means no tensor parallelism (`-sm tensor` hard-requires FA: `src/llama-context.cpp`), so the second card cannot add bandwidth today.

## B. Levers, ranked (gain per effort, lossless first)

| # | Lever | Expected gain | Quality risk | Downtime? | Effort | Evidence |
|---|---|---|---|---|---|---|
| 1 | **Tensor parallel** `-sm tensor` on a new build with FA (both cards read half the weights at once) | SOURCE (2× V100, PCIe 3.0 **x8**, same model UD-Q4_K_M, FA on, q8_0 KV, MTP n-max 2, master 8e33095, 2026-09-13): decode **+32%** at depth 0 (63.3 → 83.8 t/s), +40% at 32K (51.9 → 72.6), +46% at 64K; prefill **-12%** at depth 0-32K (795 → 699). ESTIMATE for Jarvis (f16 KV, n-max 5, x16 links): **+20-35%** decode on normal turns | Output may change at near-tie tokens (different summation order): checked by the harness | yes (windows + adoption restart) | build 40 min + one 30-min window | [split-bench README + figure](https://github.com/eightman999/llama-split-bench); qwen35 is not on the TP deny-list, but qwen4exp and glm-dsa are (`src/llama-arch.cpp`); 2-GPU all-reduce through pinned host memory, gated at Volta (`ggml/src/ggml-cuda/allreduce.cu`); [multi-GPU docs](https://github.com/ggml-org/llama.cpp/blob/master/docs/multi-gpu.md); needs `-DCMAKE_CUDA_ARCHITECTURES=70` or the all-reduce kernel is missing ([LM Studio #2354](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/2354)) |
| 2 | **Flash attention compiled in** (new build, still `-sm layer`) | Prefill ESTIMATE **+20-40%**: split-bench layer+FA 795 t/s at depth 0 (SOURCE) vs ~500-650 here; the sm70-attn fork gave +41% on 14K here (MEASURED Sep 23). Frees ~1-2 GiB per card (fork MEASURED 10,968/12,624 vs 12,962/13,644 MiB). Decode: unknown, measured by the harness | near-tie check | yes | same build + part of a window | as row 1; [PR #27997](https://github.com/ggml-org/llama.cpp/pull/27997) (draft, unmerged) shows the upstream D256 Volta config is not tuned |
| 3 | **Bigger context** once FA/TP frees VRAM (`-c 49152`-`65536`) | Not a speed change: `-c` did not change decode (MEASURED Sep 22, 16K vs 32K identical). Stops the 4-per-48 h silent truncations. ESTIMATE: f16 KV = 64 KiB/token → 64K costs 4 GiB total, split across both cards | none (f16 kept) | yes | 1 config in a window | wiki jarvis-speed-tuning; fork ran q8_0 at 65,536 with room to spare (MEASURED) |
| 4 | **DFlash2 draft** instead of the MTP head | SOURCE: +24% over MTP n-max 2 on an RTX 3090 in llama.cpp ([HF discussion](https://huggingface.co/z-lab/Qwen3.8-27B-DFlash2/discussions/9)), but llama.cpp accepts only ~2.2-3.3 tokens/step vs ~5.5 in vLLM ([z-lab/dflash #170](https://github.com/z-lab/dflash/issues/170), open). ESTIMATE vs Jarvis's tuned MTP n5/p0.4: **-10% to +20%**. Draft 1.1 GB (Q4_K_M) / 2.06 GB (Q8_0) ([incoai GGUF](https://huggingface.co/incoai/Qwen3.8-27B-DFlash2-GGUF)) | near-tie check | yes | 9-min download + configs in a window | stock build has `--spec-type draft-dflash` ([PR #22105](https://github.com/ggml-org/llama.cpp/pull/22105)) |
| 5 | **Re-tune MTP** (n-max 3/4/6, p-min 0.3/0.5) on whichever base wins | ESTIMATE ±5-10% per workload (MEASURED Sep 21: p-min 0.4 +10% reasoning, -5% predictable; n5 best with layer split). With TP the verify pass gets cheaper, so the best n-max may move | near-tie check | yes | configs in a window | wiki jarvis-speed-tuning, [discussion #25198](https://github.com/ggml-org/llama.cpp/discussions/25198) |
| 6 | **CUDA graphs** (the Sep 21 unit set `GGML_CUDA_DISABLE_GRAPHS=1`; VERIFY it is still set, E2) | ESTIMATE 0-8% decode: graphs are allowed on Volta (only pre-Volta is blocked), but they need two identical calls in a row, and MTP verify batches vary in size | none (same kernels) | yes | 1 config | `ggml/src/ggml-cuda/ggml-cuda.cu` `ggml_cuda_graph_set_enabled` (SOURCE) |
| 7 | **Open WebUI background tasks off** (title/tags/follow-up) | Removes 1-3 extra 27B requests after every answer. They compete with your next message and fill the shared 24,576-token KV pool. ESTIMATE: lower time-to-first-token when you reply quickly | none | no (UI setting) | 5 min | [Open WebUI task models](https://docs.openwebui.com/features/administration/task-models/); wiki jarvis-speed-tuning says they were still firing |
| 8 | `--cache-ram 32768` (host RAM prompt cache, default 8192 MiB) | Faster switching between 3+ conversations: restore from RAM instead of re-prefilling. ESTIMATE 20K tokens: 33 s re-prefill at 600 t/s → ~1 s restore | none | yes (restart) | adopt-time flag | server `--cache-ram` / `--cache-idle-slots` help (SOURCE, commit f4e276a) |
| 9 | Backend sampling `-bs` | ESTIMATE 0-5%. Likely fails with MTP verify: the target context allows 1 output per sequence (`n_outputs_max_per_seq = 1`, `common/common.h`) | none | yes | 1 config | SOURCE code; low priority |
| 10 | **sm70-attn forks** (fishlikeX, on the box; [Flo5k5](https://github.com/Flo5k5/sm70-attn), synced to master Sep 23 with Volta FA configs and a vocab-trimmed MTP draft) | SOURCE ([Flo5k5 PR #1](https://github.com/Flo5k5/sm70-attn/pull/1), 1× V100-32GB, MTP n4, 26K): decode 44.2 → 49.7 t/s; attention configs alone +6% decode / +41% prefill | near-tie check; unmerged fork | yes | separate build | only after rows 1-2 are measured |
| 11 | **Load time**: `-m` local file instead of `-hf` (no network check); confirm real sm_70 code, not PTX JIT | ESTIMATE seconds to ~1 min off each restart (a restart takes 90-120 s today, MEASURED Sep 21) | none | adopt-time | trivial | VERIFY E3/E4 |
| 12 | **Smaller quant** ISTA-DASLab GSQ-RCO IQ3_S (11.0 GiB) + the same MTP head (**lossy**) | ESTIMATE decode up to 1.3-1.5x (17.66 → 11.0 GiB read per pass); fits one card | **real**: gate = llama-perplexity KLD vs current Q4_K_M, top-1 ≥ 99% and mean KLD ≤ 0.01, or equal scores on Simon's quality suite | yes | 11.8 GB download + KLD run | [ISTA-DASLab 27B GSQ-RCO](https://huggingface.co/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF) (vendor: AIME25/LCB equal to BF16, GPQA-D -0.51); [GSQ-RCO + unsloth MTP merge](https://huggingface.co/cruizba/ISTA-DASLab-Qwen3.8-27B-GSQ-RCO-GGUF-Unsloth-MTP) |
| 13 | Shorter reasoning (`high` instead of `xhigh`) (**lossy**) | xhigh uses ~3.3x the thinking tokens of low (MEASURED Sep 23), so time-to-answer drops a lot | real (AA index 34 at xhigh vs 22 non-reasoning) | no (per request) | per-request `chat_template_kwargs` already works | gate: quality suite; Simon's call, not in the runbook |
| - | Does **not** apply | ngram + MTP: on this hybrid model an n-gram rejection forces a checkpoint restore and replay, because rollback snapshots = MTP n-max only (`common/common.h need_n_rs_seq`, SOURCE). That explains the MEASURED -37%. `--cache-reuse`: the recurrent state cannot be spliced (`llama-memory-recurrent.cpp seq_rm` only rolls back the tail, SOURCE). ik_llama.cpp: no Volta support ([#2463](https://github.com/ikawrakow/ik_llama.cpp/issues/2463)). vLLM ≥ 0.20, SGLang, ExLlamaV3, TensorRT-LLM: no sm_70 (wiki v100-speed-frontier). The V100 vLLM fork [1Cat-vLLM](https://github.com/1CatAI/1Cat-vLLM) only publishes 4-card numbers. Power 250 W, ECC, THP, NUMA, governor: no effect on a GPU-resident model (MEASURED Sep 23 for power; the rest are CPU-side). `GGML_CUDA_P2P`: measured no-op on the 2× V100 split-bench box (SOURCE) | | | | |

Known risk while testing a new build: [llama.cpp #29255](https://github.com/ggml-org/llama.cpp/issues/29255) (open) reports random "CUDA error: invalid argument" on Volta with layer split, large prefills and partial prefix reuse. If Jarvis ever crashes with that text, it is this bug, not a config error.

### Hardware upgrades (separate, costed; Simon's money, none recommended now)
| Option | Cost (Sep 2026, asking prices) | What it buys for this model |
|---|---|---|
| 2× V100 32GB PCIe replacing the 16 GB cards | $634 low, ~$890 average per card ([gpupoet](https://gpupoet.com/gpu/shop/nvidia-tesla-v100-32gb), [gpudojo](https://gpudojo.com/tesla-v100)) → ~$1.3-1.8K minus resale of the 16 GB cards | Same bandwidth, so no decode gain alone. The 27B fits one card (frees the other), or TP with full 262K context |
| Dual-V100 SXM2 NVLink carrier board + 2× V100 SXM2 | board $233-343 on eBay ([example](https://www.ebay.com/itm/128019227164)); a review claims 64 GB for ~$700 total ([Miya Gadget](https://miyagadget.page/en/blog/2026/09/17/tesla-v100-dual-sxm2-nvlink-review-en/)); cards VERIFY | NVLink 300 GB/s instead of pinned-host PCIe for the TP all-reduce: ESTIMATE +5-15% over PCIe TP. Fit, power and cooling in the HYVE G2GPU12 chassis: VERIFY (no public spec found; E7) |
| 3rd/4th GPU for 4-way TP | card cost + a 240 V circuit | llama.cpp's built-in all-reduce is 2-GPU only (`allreduce.cu`), so 4-way needs NCCL. The box is already near the 120 V circuit limit at full load (wiki power page). Not recommended |

## C. Runbook

Order: deliver scripts → read-only baseline → build (no downtime) → downtime windows, one lever each → adopt → re-check. You can batch several window steps into one downtime by listing more config names on one command line. The harness always runs `ref` (speculation off, stored after the first time) and `ctl` (the exact production config) first.
Test folders: `~/speed/` and `~/llama.cpp-tp/`. Timestamps printed by the harness are UTC; Central (CDT) = UTC-5.

```text
JARVIS STEP 27B-1 of 14: deliver the two test scripts (SIMON STEP)
SIMON STEP - Jarvis must not run this (long file delivery breaks Jarvis's tool-call JSON).
Goal: put ~/speed/scripts/j27_logstats.py (read-only journal summary) and ~/speed/scripts/t27_window.py (downtime-window tester) on jarvis-1.
Precondition (read-only): ls -d ~/speed 2>/dev/null || echo "no ~/speed yet"  -> either answer is fine.
Do (Simon): open docs/speed-research/scripts/deliver-27b.sh on branch claude/speed-research, copy ALL of it, paste it into your SSH terminal as simon. The echo may look garbled; trust the checksum lines.
Takes: 1 minute.
Expected last lines:
  j27_logstats.py: 77 lines, 3464 bytes, fb7817288dbaffa2
  t27_window.py: 390 lines, 22533 bytes, 05d965589667b06d
PASS: both lines match exactly. FAIL: a number differs -> paste the block again (it overwrites the two files).
Jarvis check afterwards (read-only): sha256sum ~/speed/scripts/*.py | cut -c1-16
Undo: rm ~/speed/scripts/j27_logstats.py ~/speed/scripts/t27_window.py  (only with Simon's yes)
save_finding(topic="speed-27b", finding="27B-1 scripts delivered: j27_logstats fb7817288dbaffa2, t27_window 05d965589667b06d, PASS/FAIL", source="~/speed/scripts")
```

```text
JARVIS STEP 27B-2 of 14: baseline speed and facts (read-only, no downtime)
Goal: record today's real Jarvis speed from the journal and settle 3 facts: is flash attention (FA) compiled into the production binary, does the unit disable CUDA graphs, how long a restart takes.
Preconditions (read-only):
 a) ls ~/speed/scripts/j27_logstats.py   -> exists (step 27B-1)
 b) systemctl is-active llama-server   -> active
Commands (one at a time, each prints a short summary):
 1) systemctl show -p Environment llama-server
 2) grep -E '^(GGML_CUDA_FA|CMAKE_CUDA_ARCHITECTURES|BUILD_SHARED_LIBS):' ~/llama.cpp/build/CMakeCache.txt
 3) ls -l --time-style=+%F_%H:%M ~/llama.cpp/build/bin/ | grep -E 'libggml-cuda|llama-server$'
 4) ls -l --time-style=+%F_%H:%M ~/llama.cpp/build/CMakeCache.txt
 5) journalctl -u llama-server -b -o cat --no-pager | grep -m4 -iE 'flash attn|flash attention'
 6) nvidia-smi --query-gpu=index,memory.used,memory.total,temperature.gpu,power.limit --format=csv,noheader
 7) journalctl -u llama-server --since "-48h" -o cat --no-pager | python3 ~/speed/scripts/j27_logstats.py
 8) journalctl -u llama-server -b -o short-precise --no-pager | grep -E 'loading model|speculative_init|warming up|server is listening' | tail -6 | cut -c1-150
Takes: 1-2 minutes.
Expected: (1) GGML_CUDA_DISABLE_GRAPHS=1 or nothing; (2) GGML_CUDA_FA:BOOL=ON or OFF plus the CUDA arch list; (5) "Flash Attention not supported, set to disabled"; (6) each GPU ~13,900-14,200 MiB of 16,384; (7) decode p50 roughly 30-55 t/s, prefill p50 roughly 400-650 t/s, truncation count; (8) load start and "server is listening" times (restart time = the difference).
PASS: all 8 ran and the numbers are saved (baseline only). FAIL: a command errors -> save the error text; do not retry with longer commands.
Meaning: GGML_CUDA_FA OFF, or a CUDA library older than the CMakeCache, means FA was compiled out -> step 27B-3 fixes it. GGML_CUDA_DISABLE_GRAPHS=1 -> step 27B-4 tests removing it.
Undo: nothing (read-only).
save_finding(topic="speed-27b", finding="27B-2 baseline <date> CT: decode p50 _ (weighted _) t/s, prefill p50 _ t/s, prompt-eval p50 _ ms, truncations _, VRAM _/_ MiB, env _, FA compiled _, CUDA archs _, restart _ s", source="journalctl llama-server 48h")
```

```text
JARVIS STEP 27B-3 of 14: build current llama.cpp with flash attention for V100 (no downtime)
Goal: a second build at ~/llama.cpp-tp (master 4b1a27f, 2026-09-25, includes the sm_70 FA compile fix) with FA for sm_70. Needed for FA, tensor-parallel and DFlash tests. Production ~/llama.cpp is not touched.
Preconditions (read-only):
 a) systemctl list-units --type=service --state=active --no-legend --plain | grep -E '^(bench-|mtp-test|il-beside|glm-test|fn-test|t27-|big-verify|build-|dl-)' || echo NONE-ACTIVE   -> NONE-ACTIVE (a build distorts CPU benchmarks)
 b) ls -d /usr/local/cuda*; /usr/local/cuda/bin/nvcc --version | tail -1   -> includes a 12.9 folder, "release 12.9" (if /usr/local/cuda is missing, use the cuda-12.9 path in command 2 instead)
 c) test -e ~/llama.cpp-tp && echo EXISTS || echo FREE   -> FREE
 d) df -h /home | tail -1   -> at least 5G available
Commands:
 1) git init -q ~/llama.cpp-tp && git -C ~/llama.cpp-tp fetch -q --depth 1 https://github.com/ggml-org/llama.cpp 4b1a27fa0eb875bbca4f6cfe936e3d65adc685c0 && git -C ~/llama.cpp-tp checkout -q FETCH_HEAD && git -C ~/llama.cpp-tp log -1 --format='%h %cd' --date=short
    expect: 4b1a27f 2026-09-25 (about 37 MB download)
 2) sudo systemd-run --unit=build-tp -p User=simon -p Group=simon -p Nice=10 -p WorkingDirectory=/home/simon/llama.cpp-tp /bin/bash -c 'cmake -S . -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=70 -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc -DCMAKE_BUILD_TYPE=Release >cfg.log 2>&1 && cmake --build build -j 36 --target llama-server llama-bench llama-perplexity >build.log 2>&1'
 3) every ~5 min: systemctl is-active build-tp; tail -c 300 ~/llama.cpp-tp/build.log
 4) when inactive: systemctl show build-tp -p Result; ls ~/llama.cpp-tp/build/bin | grep -E '^llama-(server|bench|perplexity)$'
 5) grep -E '^(GGML_CUDA_FA|CMAKE_CUDA_ARCHITECTURES):' ~/llama.cpp-tp/build/CMakeCache.txt
 6) /usr/local/cuda/bin/cuobjdump --list-elf ~/llama.cpp-tp/build/bin/libggml-cuda.so | head -2
 7) CUDA_VISIBLE_DEVICES= ~/llama.cpp-tp/build/bin/llama-server --version 2>&1 | tail -2
Takes: ~30-50 min (ESTIMATE; the CUDA FA kernels dominate). It is a unit, so an SSH drop cannot stop it.
Expected: three binaries; GGML_CUDA_FA:BOOL=ON and CMAKE_CUDA_ARCHITECTURES:STRING=70; cuobjdump lines contain sm_70; version shows 4b1a27f.
PASS: all of the above. FAIL: build.log has errors -> grep -m5 -iE ' error|Error ' ~/llama.cpp-tp/build.log | cut -c1-200, save it, stop and tell Simon (do not try other commits on your own).
Undo: sudo systemctl stop build-tp (only while it runs). Deleting ~/llama.cpp-tp needs Simon's yes.
save_finding(topic="speed-27b", finding="27B-3 build-tp 4b1a27f: PASS/FAIL, FA _, arch _, took _ min", source="~/llama.cpp-tp/build.log")
```

```text
JARVIS STEP 27B-4 of 14: window 1 - control run and CUDA graphs (SIMON ONLY)
SIMON ONLY - Jarvis must not run this: it stops llama-server (Jarvis) for ~30 min. The script always starts it again at the end, also on errors.
Goal: measure the exact production config ("ctl") on the test harness, store the speculation-off reference ("ref", run twice to prove the output is repeatable), and test CUDA graphs ("graphs" = ctl without GGML_CUDA_DISABLE_GRAPHS). If step 27B-2 showed no such variable, still run it: graphs then equals ctl and shows run-to-run noise.
Preconditions (Jarvis may run these read-only checks first):
 a) sha256sum ~/speed/scripts/t27_window.py | cut -c1-16   -> 05d965589667b06d
 b) systemctl list-units --type=service --state=active --no-legend --plain | grep -E '^(bench-|mtp-test|il-beside|glm-test|fn-test|t27-|big-verify|build-|dl-)' || echo NONE-ACTIVE   -> NONE-ACTIVE
 c) curl -s -m 5 localhost:8081/health || echo PORT-FREE   -> PORT-FREE
 d) ls ~/.cache/huggingface/hub/models--ggml-org--Qwen3.8-27B-GGUF/snapshots/*/Qwen3.8-27B-Q4_K_M.gguf ~/models/mtp-Qwen3.8-27B-Q4_0.gguf   -> both exist
Simon runs (one line):
 sudo systemd-run --unit=t27-window --collect -p RuntimeMaxSec=7800 -p TimeoutStopSec=900 -p "ExecStopPost=/bin/sh -c 'systemctl stop t27-srv; systemctl start llama-server'" /usr/bin/python3 /home/simon/speed/scripts/t27_window.py graphs
 (if systemd-run rejects the ExecStopPost property, run the same line without that -p "..." part; the script restores Jarvis by itself)
Watch: journalctl -u t27-window -n 20 --no-pager      Abort early (restores Jarvis): sudo systemctl stop t27-window
Takes: ~30 min the first time (ref runs every prompt twice); Jarvis is offline the whole time.
Expected: the journal ends with "Jarvis restored: yes, healthy after N s". Then Jarvis reads: cat $(ls -d ~/speed/results/t27/2* | tail -1)/summary.txt
 rows: ref (dec ~27-30 t/s, "reference re-run identical 4/4"), ctl (dec mean ~45-60), graphs.
PASS (graphs): dec mean >= ctl +3% AND long >= ctl AND VRAM <= 15300/15300 AND "vs prod ref" only I or T (near-tie, gap <= 0.100) AND qual equal to ref's. Otherwise FAIL.
Also record: ref must show re-run identical 4/4; if not, the reference is not repeatable -> tell Simon before trusting any identity check.
Undo: nothing (production files untouched). If Jarvis did not come back: sudo systemctl start llama-server; journalctl -u llama-server -n 30 --no-pager
save_finding(topic="speed-27b", finding="27B-4 window1: ref dec _ (rerun _/4), ctl dec _ long _ pp6k _ 16K tg _ VRAM _/_ acc _, graphs dec _ (_%) PASS/FAIL", source="~/speed/results/t27/<time>/summary.txt")
```

```text
JARVIS STEP 27B-5 of 14: window 2 - flash attention in the new build (SIMON ONLY)
SIMON ONLY - Jarvis must not run this: it stops Jarvis for ~30 min and restarts it at the end.
Goal: measure the new build with FA on, same layer split and flags as production ("new-ctl"). "new-faoff" is the same binary with FA forced off, so the build effect and the FA effect can be told apart. "new-ref" (speculation off, new build) is added automatically.
Preconditions (read-only, Jarvis):
 a) step 27B-3 PASS: ls ~/llama.cpp-tp/build/bin/llama-server
 b) the NONE-ACTIVE and PORT-FREE checks from step 27B-4 -> NONE-ACTIVE, PORT-FREE
Simon runs:
 sudo systemd-run --unit=t27-window --collect -p RuntimeMaxSec=7800 -p TimeoutStopSec=900 -p "ExecStopPost=/bin/sh -c 'systemctl stop t27-srv; systemctl start llama-server'" /usr/bin/python3 /home/simon/speed/scripts/t27_window.py new-ctl new-faoff
Takes: ~35 min (ref is reused; ctl, new-ref, new-ctl, new-faoff are measured).
After it, Jarvis (read-only, one command):
 D=$(ls -d ~/speed/results/t27/2* | tail -1); cat $D/summary.txt; grep -m3 -iE 'flash attn|flash attention' $D/new-ctl.log | cut -c1-160
 -> the grep must show FA enabled (not "set to disabled")
Expected: new-ctl pp6k and 16K pp clearly above ctl; VRAM lower than ctl.
PASS: new-ctl pp6k >= ctl +15% AND new-ctl dec mean >= ctl -3% AND VRAM <= 15300/15300 AND vs prod ref only I/T AND qual equal. FAIL otherwise (report which rule failed).
If dec drops but prefill rises: that is a trade, Simon decides; the tensor-parallel step still needs this build.
Undo: nothing (production untouched).
save_finding(topic="speed-27b", finding="27B-5 FA: new-ctl dec _ vs ctl _, pp6k _ vs _, 16K pp _ vs _, VRAM _/_ vs _/_, new-faoff dec _ -> PASS/FAIL", source="~/speed/results/t27/<time>/summary.txt")
```

```text
JARVIS STEP 27B-6 of 14: window 3 - tensor parallel across both V100s (SIMON ONLY)
SIMON ONLY - Jarvis must not run this: it stops Jarvis for ~35 min and restarts it at the end.
Goal: split every layer across both cards (-sm tensor, FA on) so both HBM stacks work on every token. Configs: "new-tp-ref" (TP, speculation off), "new-tp" (TP + production MTP flags), "new-tp-ts" (TP with a 46/54 split, because the MTP draft sits on CUDA0).
Preconditions (read-only, Jarvis): step 27B-5 showed FA enabled in new-ctl.log; NONE-ACTIVE; PORT-FREE (commands as in step 27B-4).
Simon runs:
 sudo systemd-run --unit=t27-window --collect -p RuntimeMaxSec=7800 -p TimeoutStopSec=900 -p "ExecStopPost=/bin/sh -c 'systemctl stop t27-srv; systemctl start llama-server'" /usr/bin/python3 /home/simon/speed/scripts/t27_window.py new-tp-ref new-tp new-tp-ts
Takes: ~40 min.
After it, Jarvis (read-only, one command):
 D=$(ls -d ~/speed/results/t27/2* | tail -1); cat $D/summary.txt; grep -m4 -iE 'tensor|all.?reduce|NCCL|error' $D/new-tp.log | cut -c1-160
Expected (SOURCE, 2x V100 PCIe x8): TP decode +32% at depth 0 and more at 16K; prefill about -12%.
PASS: new-tp dec mean >= best of (ctl, new-ctl) +10% AND 16K tg >= ctl +10% AND VRAM <= 15300 on both GPUs AND vs prod ref only I/T AND qual equal. new-tp-ts replaces new-tp if it passes too and has lower CUDA0 VRAM. FAIL: any rule broken, or the server did not start (grep the log for "SPLIT_MODE_TENSOR").
Undo: nothing (production untouched).
save_finding(topic="speed-27b", finding="27B-6 TP: new-tp-ref dec _, new-tp dec _ (+_% vs ctl), 16K tg _, pp6k _, VRAM _/_; new-tp-ts _ -> PASS/FAIL", source="~/speed/results/t27/<time>/summary.txt")
```

```text
JARVIS STEP 27B-7 of 14: window 4 - re-tune MTP draft length on the winning base (SIMON ONLY)
SIMON ONLY - Jarvis must not run this: it stops Jarvis for ~40 min and restarts it at the end.
Goal: the best --spec-draft-n-max / --spec-draft-p-min can move once the verify pass is cheaper (TP) or the build changes. Production today: n-max 5, p-min 0.4.
Pick the base B = new-tp if 27B-6 passed, else new-ctl if 27B-5 passed, else ctl.
Preconditions (read-only, Jarvis): NONE-ACTIVE; PORT-FREE (as in 27B-4).
Simon runs (replace B; four variants, each changes one flag):
 sudo systemd-run --unit=t27-window --collect -p RuntimeMaxSec=7800 -p TimeoutStopSec=900 -p "ExecStopPost=/bin/sh -c 'systemctl stop t27-srv; systemctl start llama-server'" /usr/bin/python3 /home/simon/speed/scripts/t27_window.py B B@--spec-draft-n-max=4 B@--spec-draft-n-max=6 B@--spec-draft-p-min=0.3 B@--spec-draft-p-min=0.5
Takes: ~45 min.
After it, Jarvis: D=$(ls -d ~/speed/results/t27/2* | tail -1); cat $D/summary.txt
PASS for a variant: dec mean >= B +3% AND long >= B -3% AND VRAM <= 15300 AND vs prod ref only I/T AND qual equal. Keep B if no variant passes. Note reasoning vs copy separately (the first dec number is reasoning, second copy, third prose): p-min trades one for the other.
Undo: nothing.
save_finding(topic="speed-27b", finding="27B-7 MTP retune on B=_: n4 _, n6 _, pmin0.3 _, pmin0.5 _ vs B _ -> keep _", source="~/speed/results/t27/<time>/summary.txt")
```

```text
JARVIS STEP 27B-8 of 14: download the DFlash2 draft (Jarvis, no downtime; needs Simon's yes)
Goal: fetch the Q8_0 DFlash2 draft for Qwen3.8-27B (about 2.06 GB) to ~/speed/models/dflash2-27b.gguf and verify it.
Preconditions (read-only):
 a) df -h /home | tail -1   -> at least 5G available
 b) NONE-ACTIVE check from 27B-3 -> NONE-ACTIVE (a download slows nothing, but keep the box quiet)
Commands:
 1) curl -s https://huggingface.co/api/models/incoai/Qwen3.8-27B-DFlash2-GGUF/tree/main | python3 -c "import json,sys;[print(f['path'],f.get('size'),(f.get('lfs') or {}).get('oid','')[:16]) for f in json.load(sys.stdin)]"
    -> lists the files. Pick the Q8_0 .gguf (~2.06 GB); note its exact NAME and the 16-hex sha start.
 2) sudo systemd-run --unit=dl-dflash2 -p User=simon -p Group=simon /usr/bin/curl -fL --retry 5 -o /home/simon/speed/models/dflash2-27b.gguf https://huggingface.co/incoai/Qwen3.8-27B-DFlash2-GGUF/resolve/main/NAME
 3) every few min: systemctl is-active dl-dflash2; ls -l ~/speed/models/dflash2-27b.gguf
 4) sha256sum ~/speed/models/dflash2-27b.gguf | cut -c1-16
Takes: ~9 min at 4 MB/s.
Expected: size equals the listed size; sha start equals the oid start from command 1.
PASS: size and sha match. FAIL: mismatch -> rm ~/speed/models/dflash2-27b.gguf (a partial download in a test folder) and repeat once; then tell Simon.
Undo: rm ~/speed/models/dflash2-27b.gguf (test folder only).
save_finding(topic="speed-27b", finding="27B-8 DFlash2 draft NAME, size _, sha256 _ : PASS/FAIL", source="huggingface.co/incoai/Qwen3.8-27B-DFlash2-GGUF")
```

```text
JARVIS STEP 27B-9 of 14: window 5 - DFlash2 draft vs MTP (SIMON ONLY)
SIMON ONLY - Jarvis must not run this: it stops Jarvis for ~35 min and restarts it at the end.
Goal: replace the MTP head with the DFlash2 block drafter (drafts a whole block per pass). Sources: +24% over MTP n-max 2 on an RTX 3090, but llama.cpp accepts only ~2-3 tokens/step (z-lab/dflash #170), so it may not beat the tuned MTP here.
Preconditions (read-only, Jarvis): step 27B-8 PASS (ls -l ~/speed/models/dflash2-27b.gguf); NONE-ACTIVE; PORT-FREE.
Simon runs ONE of these (the base that won so far):
 if tensor parallel won:  ... t27_window.py new-tp new-tp-dflash new-tp-dflash@--spec-draft-n-max=7
 else (layer split):      ... t27_window.py dflash5 dflash7
 (the "..." is: sudo systemd-run --unit=t27-window --collect -p RuntimeMaxSec=7800 -p TimeoutStopSec=900 -p "ExecStopPost=/bin/sh -c 'systemctl stop t27-srv; systemctl start llama-server'" /usr/bin/python3 /home/simon/speed/scripts/t27_window.py)
Takes: ~35 min.
After it, Jarvis: D=$(ls -d ~/speed/results/t27/2* | tail -1); cat $D/summary.txt; grep -m3 -iE 'dflash|error' $D/*dflash*.log | cut -c1-160
PASS: a DFlash2 row has dec mean >= the matching MTP row +5% AND long >= MTP row -5% AND VRAM <= 15300 AND vs prod ref only I/T AND qual equal. FAIL otherwise; keep MTP.
Undo: nothing (production untouched).
save_finding(topic="speed-27b", finding="27B-9 DFlash2: dec _ vs MTP _, acc _, VRAM _/_ -> PASS/FAIL", source="~/speed/results/t27/<time>/summary.txt")
```

```text
JARVIS STEP 27B-10 of 14: window 6 - bigger context window (SIMON ONLY)
SIMON ONLY - Jarvis must not run this: it stops Jarvis for ~25 min and restarts it at the end.
Goal: with FA (and TP) the attention buffers shrink, so the window can grow past 24,576 and stop the silent truncations (4 in 48 h). -c does not change decode speed (MEASURED Sep 22); this step checks VRAM.
Preconditions (read-only, Jarvis): 27B-5 or 27B-6 PASS; NONE-ACTIVE; PORT-FREE.
Simon runs ONE of these:
 TP won:    ... t27_window.py new-tp-c64k new-tp@-c=49152
 layer won: ... t27_window.py new-c64k new-ctl@-c=49152
 (... = the same sudo systemd-run prefix as in step 27B-9)
Takes: ~25 min.
After it, Jarvis: D=$(ls -d ~/speed/results/t27/2* | tail -1); cat $D/summary.txt
PASS for a size: server started AND VRAM peak <= 15300 on both GPUs (this includes the 16K-depth test) AND dec mean within 3% of the same config at -c 24576. Choose the largest size that passes. FAIL: VRAM above 15300 -> keep the smaller size.
Note for adoption: Open WebUI's jarvis model num_ctx must be changed to the same number (step 27B-12).
Undo: nothing.
save_finding(topic="speed-27b", finding="27B-10 context: 64K VRAM _/_, 48K VRAM _/_ -> choose -c _", source="~/speed/results/t27/<time>/summary.txt")
```

```text
JARVIS STEP 27B-11 of 14: stop Open WebUI background generations (SIMON ONLY, UI setting)
SIMON ONLY - Jarvis must not change Open WebUI settings.
Goal: after each answer Open WebUI asks the 27B for a title, tags and follow-up questions. That is 1-3 extra requests that compete with your next message and fill the shared KV pool.
Precondition (Jarvis, read-only): Simon sends 3 short messages that need no tools; then: journalctl -u llama-server --since "-10 min" -o cat --no-pager | grep -c "prompt eval time"   -> note the count (expect 6-12 if the tasks still fire)
Simon: Open WebUI > Admin Panel > Settings > Interface: turn OFF Title Generation, Tags Generation, Follow Up Generation and Autocomplete Generation (leave Query Generation on only if you use web search or knowledge). Save. No container restart.
Test (Jarvis, read-only): Simon sends 3 new short no-tool messages; journalctl -u llama-server --since "-5 min" -o cat --no-pager | grep -c "prompt eval time"
Takes: 5 minutes.
PASS: the count equals the number of messages (3). FAIL: more -> the toggles are overridden somewhere else; tell Simon (earlier config-table edits did not stick, wiki jarvis-speed-tuning).
Undo: turn the toggles back on in the same page.
save_finding(topic="speed-27b", finding="27B-11 Open WebUI tasks: requests per 3 messages before _ after _ -> PASS/FAIL", source="journalctl llama-server")
```

```text
JARVIS STEP 27B-12 of 14: adopt the winning config (SIMON ONLY)
SIMON ONLY - Jarvis must not run this: it restarts Jarvis and changes the production service.
Goal: switch production to the flags that PASSED in steps 27B-4..10, without editing the original unit (a drop-in file), with a one-line rollback.
Preconditions: each chosen lever has a PASS row this week; the winning command line is written from section D of docs/speed-research/qwen3.8-27b.md (edit its -sm, -c, spec flags to the winners).
Simon runs:
 1) sudo cp /etc/systemd/system/llama-server.service /etc/systemd/system/llama-server.service.pre-speed27b
 2) sudo mkdir -p /etc/systemd/system/llama-server.service.d
 3) sudo tee /etc/systemd/system/llama-server.service.d/speed27b.conf >/dev/null <<'SPEED27B_END'
[Service]
UnsetEnvironment=GGML_CUDA_DISABLE_GRAPHS
ExecStart=
REPLACE THIS WHOLE LINE WITH THE ExecStart=/usr/bin/numactl ... LINE FROM SECTION D
SPEED27B_END
    (drop the UnsetEnvironment line if step 27B-4 failed)
 4) sudo systemctl daemon-reload && sudo systemctl restart llama-server
 5) after 180 s: curl -s localhost:8080/health   -> {"status":"ok"}
 6) if -c changed: Open WebUI > Workspace > Models > jarvis > Advanced Params > Context Length = the new -c (mandatory, or the UI asks for a window the server does not have)
Then Jarvis (read-only): nvidia-smi --query-gpu=index,memory.used --format=csv,noheader; journalctl -u llama-server -b -o cat --no-pager | grep -m4 -iE 'flash|tensor|speculative_init|error'
Takes: 10 minutes; Jarvis offline ~3 min.
PASS: health ok within 180 s; VRAM <= 15300 MiB per GPU during a long chat; normal answers.
FAIL or any doubt -> rollback (one line): sudo mv /etc/systemd/system/llama-server.service.d/speed27b.conf /home/simon/speed/speed27b.conf.off && sudo systemctl daemon-reload && sudo systemctl restart llama-server   (and set num_ctx back if you changed it)
save_finding(topic="speed-27b", finding="27B-12 adopted <date> CT: flags _, VRAM _/_, health ok after _ s", source="/etc/systemd/system/llama-server.service.d/speed27b.conf")
```

```text
JARVIS STEP 27B-13 of 14: check the adopted config after 48 hours (read-only)
Goal: confirm the gain holds in real use and nothing crashes.
Preconditions (read-only): ls /etc/systemd/system/llama-server.service.d/speed27b.conf   -> exists; at least 48 h since step 27B-12.
Commands:
 1) journalctl -u llama-server --since "-48h" -o cat --no-pager | python3 ~/speed/scripts/j27_logstats.py
 2) journalctl -u llama-server --since "-48h" -o cat --no-pager | grep -c -E 'CUDA error|ggml_abort|out of memory'
 3) nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
Takes: 1 minute.
Compare with the step 27B-2 finding (memory_search "27B-2 baseline").
PASS: token-weighted decode >= baseline x 1.10 (if tensor parallel was adopted; >= baseline if only FA) AND command 2 prints 0 AND truncated=1 events fewer than baseline if -c grew. FAIL: tell Simon; rollback is in step 27B-12.
Undo: nothing (read-only).
save_finding(topic="speed-27b", finding="27B-13 after 48 h: decode p50 _ (baseline _), weighted _, prefill p50 _, truncations _, crash lines _ -> PASS/FAIL", source="journalctl llama-server 48h")
```

```text
JARVIS STEP 27B-14 of 14: OPTIONAL lossy lever - smaller quant with a KL-divergence gate (download: Jarvis; test: SIMON ONLY)
Goal: test ISTA-DASLab GSQ-RCO IQ3_S (11.0 GiB, vs 17.66 GiB now) with the same MTP head. Only adopt if it passes the gate: top-1 agreement >= 99% AND mean KLD <= 0.01 against the current Q4_K_M, OR equal scores on Simon's quality suite (not built yet).
Part A (Jarvis, needs Simon's yes; no downtime):
 1) curl -s https://huggingface.co/api/models/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF/tree/main | python3 -c "import json,sys;[print(f['path'],f.get('size')) for f in json.load(sys.stdin)]"   -> find the IQ3_S file (~11.8 GB)
 2) sudo systemd-run --unit=dl-iq3s -p User=simon -p Group=simon /usr/bin/curl -fL --retry 5 -o /home/simon/speed/models/27b-iq3s.gguf https://huggingface.co/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF/resolve/main/NAME
 3) cd ~/speed && sh ~/llama.cpp-tp/scripts/get-wikitext-2.sh && ls -l ~/speed/wikitext-2-raw/wiki.test.raw
Part B (SIMON ONLY - stops Jarvis ~40 min; runs as a unit that starts Jarvis again when it ends):
 sudo systemctl stop llama-server; mkdir -p ~/speed/kld
 sudo systemd-run --unit=t27-kld -p User=simon -p Group=simon -p MemoryMax=64G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p WorkingDirectory=/home/simon/speed -p "ExecStopPost=+/bin/systemctl start llama-server" /bin/bash -c 'P=/home/simon/llama.cpp-tp/build/bin/llama-perplexity; M=$(ls /home/simon/.cache/huggingface/hub/models--ggml-org--Qwen3.8-27B-GGUF/snapshots/*/Qwen3.8-27B-Q4_K_M.gguf); W=wikitext-2-raw/wiki.test.raw; $P -m $M -f $W -c 512 --chunks 40 -ngl 99 -ts 28,36 --kl-divergence-base kld/q4km.kld >kld/base.log 2>&1 && $P -m models/27b-iq3s.gguf -f $W -c 512 --chunks 40 -ngl 99 --kl-divergence-base kld/q4km.kld --kl-divergence >kld/iq3s.log 2>&1'
 Afterwards (Jarvis, read-only): systemctl is-active llama-server; grep -iE 'mean +kld|same top' ~/speed/kld/iq3s.log | head -4
Takes: download ~50 min at 4 MB/s; KLD runs ~20-40 min; the .kld file is several GB (test folder).
PASS: "Same top p" >= 99% AND "Mean KLD" <= 0.01. FAIL: keep Q4_K_M (expected: two different 3.5- and 4.9-bit quants usually differ by more than 0.01 KLD - ESTIMATE). If PASS, speed-test it with the harness: t27_window.py ctl@-m=/home/simon/speed/models/27b-iq3s.gguf
Undo: rm the files in ~/speed/models and ~/speed/kld (test folders; Simon's yes).
save_finding(topic="speed-27b", finding="27B-14 IQ3_S gate: same-top _%, mean KLD _ -> PASS/FAIL", source="~/speed/kld")
```

## D. Proposed final config (PROPOSED until steps 27B-4..10 measure it)

If tensor parallel passes (27B-6), with the 27B-10 context size and the 27B-7 draft settings:

```
ExecStart=/usr/bin/numactl --cpunodebind=0 --membind=0 /home/simon/llama.cpp-tp/build/bin/llama-server -m /home/simon/.cache/huggingface/hub/models--ggml-org--Qwen3.8-27B-GGUF/snapshots/efbb3b1f70a21d97fd4495240648405f7228554f/Qwen3.8-27B-Q4_K_M.gguf -ngl 99 -sm tensor -fa on -fit off -ctk f16 -ctv f16 -c 49152 --host 0.0.0.0 --port 8080 --jinja --chat-template-kwargs '{"reasoning_effort":"xhigh"}' --no-mmproj --no-reasoning-preserve --spec-type draft-mtp -md /home/simon/models/mtp-Qwen3.8-27B-Q4_0.gguf --spec-draft-n-max 5 --spec-draft-p-min 0.4 -devd CUDA0 -ngld 99 --parallel 2 --kv-unified --cache-ram 32768
```

If tensor parallel fails but FA passes (27B-5): the same line with `-sm layer -ts 28,36` in place of `-sm tensor -fa on -fit off`.
If DFlash2 passes (27B-9): replace `--spec-type draft-mtp -md .../mtp-Qwen3.8-27B-Q4_0.gguf --spec-draft-n-max 5 --spec-draft-p-min 0.4` with `--spec-type draft-dflash -md /home/simon/speed/models/dflash2-27b.gguf --spec-draft-n-max <winner>`.
The snapshot hash in the `-m` path must match the box (VERIFY E5). `-m` replaces `-hf` (same file, no network check at start). Open WebUI num_ctx must equal `-c`.
ESTIMATE of the combined effect vs today: decode +20-35% (TP), prefill ±0 to +25% (FA gain minus the TP prefill cost), context 24K → 48-64K. Nothing here is measured on jarvis-1 yet.

## E. Open questions and VERIFY items (each with the read-only command that settles it)

1. **Is FA compiled into the production binary?** `grep -E '^GGML_CUDA_FA:' ~/llama.cpp/build/CMakeCache.txt; ls -l --time-style=+%F_%H:%M ~/llama.cpp/build/bin/libggml-cuda.so ~/llama.cpp/build/CMakeCache.txt`. OFF, or a library older than the cache, means FA was compiled out.
2. **Does the unit still disable CUDA graphs?** `systemctl show -p Environment llama-server`
3. **Real sm_70 code or PTX JIT at load?** `/usr/local/cuda/bin/cuobjdump --list-elf ~/llama.cpp/build/bin/libggml-cuda.so | head -3` (sm_70 ELF lines = real code; none = JIT on every start, a load-time cost)
4. **Where do the 90-120 s of restart go?** `journalctl -u llama-server -b -o short-precise --no-pager | grep -E 'loading model|speculative_init|warming up|server is listening' | tail -6`
5. **Snapshot path for `-m`:** `ls ~/.cache/huggingface/hub/models--ggml-org--Qwen3.8-27B-GGUF/snapshots/`
6. **DFlash2 file name and hash:** command 1 of step 27B-8 (the HF site is blocked from this research session, so I could not list the files myself).
7. **HYVE G2GPU12 slots and PSU** (for the hardware list): `sudo dmidecode -t 9 | grep -E 'Designation|Current Usage' | head -20; sudo dmidecode -t 39 | grep -E 'Max Power|Manufacturer' | head -6`
8. **PCIe P2P between the two cards** (matters only for TP): `nvidia-smi topo -p2p r`
9. **Is `unzip` installed** (needed by get-wikitext-2.sh in 27B-14)? `command -v unzip || echo missing`
10. **Does upstream FA decode lose speed on Volta for head size 256?** Open: only the harness (27B-5, new-ctl vs new-faoff) can answer it for this box.
11. **Tensor parallel with `--parallel 2 --kv-unified` plus a separate MTP draft file:** no public report combines all three. The split-bench run used the embedded MTP head and one slot. Step 27B-6 is the test.
