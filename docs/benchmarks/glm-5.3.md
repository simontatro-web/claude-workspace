# GLM-5.3 UD-Q4_K_XL on jarvis-1: measured results

Model: unsloth GLM-5.3 UD-Q4_K_XL, 467.3 GB file, 753.9B params (40B active), from /home/simon/models (NVMe, sha256-verified).
Engine: stock llama.cpp f4e276a20 (2026-09-21), CPU backend, weights repacked at load to q4_K_8x8 (CPU model buffer 184,022 MiB + CPU_REPACK 255,744 MiB = ~430 GiB resident).
All numbers MEASURED on night 1 (2026-09-25, 05:40-13:44 UTC) with llama-bench, -lm dio, temperature n/a. t/s = tokens per second. "Beside Jarvis" = --preferred=1 with Jarvis running; "interleaved" = numactl --interleave=all with Jarvis stopped.

## Headline
| | Beside Jarvis | Interleaved (Jarvis off) |
|---|---|---|
| Decode (answer speed), empty context | 0.9-1.1 t/s | **1.48 t/s** |
| Decode at 16K context | 0.74 t/s | 1.00 t/s |
| Prefill (prompt reading), 512-token prompt, empty context | 9.9 t/s | 10.1 t/s |
| Prefill, 4096-token prompt | 7.6 t/s | 7.6 t/s |
| Prefill at 16K depth | not run | 2.5-2.8 t/s |

Decode 1.48 t/s x 24.8 GB read per token = ~37 GB/s effective, about 62% of the 59.5 GB/s STREAM measured interleaved on this box.
Prefill falls off steeply with depth (full MLA attention, no sparse indexer): reading 512 new tokens at 16K deep runs at ~2.5 t/s versus ~10 t/s on an empty context.

## Per test
### glm-a1-threads (beside Jarvis, -r 2)
| threads | prefill pp512 | decode tg64 |
|---|---|---|
| 18 | 5.71 | 0.96 |
| 32 | 9.53 | 0.86 |
| 36 | 9.87 | 0.89 |
Prefill scales with threads; decode is flat (bandwidth-bound). Decode here is lower than the same test later in the night (1.08-1.11 in a3/a5), so run-to-run placement varies; keep a baseline control in every night.

### glm-a2-batch (beside Jarvis, pp4096, -b 4096)
| ubatch | 512 | 1024 | 2048 | 4096 |
|---|---|---|---|---|
| t/s | 7.45 | 7.55 | 7.63 | 7.33 |
Batch size does not matter here (under 4%). The "up to 2x prefill" claim did not reproduce on CPU.

### glm-a3-fa (beside Jarvis)
| flash attn | pp512 d0 | tg64 d0 | pp512 d8192 | tg64 d8192 |
|---|---|---|---|---|
| on | 9.87 | 1.11 | 3.99 | 0.84 |
| off | 9.52 | 1.08 | 4.71 | 0.72 |
FA on: +17% decode at 8K depth, -15% prefill at 8K depth. Trade-off, not a free win.

### glm-a5-kcache (beside Jarvis, -fa on) - PARTIAL
f16: tg64 d0 1.09, d16384 0.74. Then "failed to create context" for -ctk q8_0 with -fa on. Quantized K cache with FA does not work for this model on this build's CPU path. Retry q8_0 with -fa off.

### glm-b1-interleave (Jarvis off)
| test | d0 | d16384 |
|---|---|---|
| pp512 | 10.07 | 2.51 |
| pp4096 | 7.56 | 2.83 |
| tg64 | **1.48** | **1.00** |
Interleaving is the biggest lever found so far for decode: +35-65% vs beside-Jarvis. Prefill unchanged.

### glm-b1-smt-prefill (Jarvis off)
pp4096: 36 threads 7.51, 72 threads 7.59. Hyperthreads add ~1%: not worth it.

### glm-b2-hybrid-* (Jarvis off) - ALL FAILED, test design errors
- -cmoe is not a llama-bench option (only -ncmoe N). Use -ncmoe 79 for "all experts on CPU".
- -ncmoe 76 and 74 failed "unable to allocate CUDA1 buffer": too many expert layers on the GPUs. Next: -ncmoe 79, then use llama-bench -fitt (auto-fit) or walk down one layer at a time.

### glm-a6-depth (beside Jarvis, tg64, fa auto) - MEASURED 2026-09-25, 32K point dropped
| depth | 0 | 4096 | 16384 |
|---|---|---|---|
| decode t/s | 1.11 | 0.93 | 0.74 |
Decode loses ~33% by 16K depth. The 16K point finished 09:59 AM CT; stopped there on purpose by a6-stopper (Simon's decision): the 32K point needed ~3.6 h of prefill and could not finish before the 4 h cap (test design error, Claude's). The runner logged it DONE (llama-bench exited 0 on stop), so the label is in queue.done. Re-run 32K later under a NEW label with a 6 h cap, or in the server harness.

### glm-a7-poll (beside Jarvis, -r 2) - MEASURED
| poll | pp512 | tg64 |
|---|---|---|
| 0 | 9.90 | 1.10 |
| 50 (default) | 9.89 | 1.10 |
| 100 | 9.87 | 1.10 |
No effect (under 0.3%). Keep the default.

Night-1 queue finished 10:28 AM CT: 7 done, 4 failed (the three hybrid jobs and a5-kcache, all test-design errors). Jarvis healthy afterwards.

## Can GLM-5.3 use its 1M context here? (ESTIMATE, 2026-09-25)
Native context is 1,048,576. KV per token at f16 ~88 KiB (SOURCE: MLA path, K only; not yet measured on the box).
| K cache | 1M tokens | weights (429.5 GiB MEASURED) + KV | fits? |
|---|---|---|---|
| f16 | ~88 GiB | ~518 GiB | no (503 GiB RAM) |
| q8_0 | ~47 GiB | ~476 GiB | only above the 465G cap, at the edge of RAM; q8_0 + FA failed on night 1 |
| q4_0 | ~25 GiB | ~455 GiB | on paper; recall cost; untested |
Under the 465G cap at f16: ~350K tokens at most, minus compute buffers (VERIFY; FA likely needed at long context).
The real wall is time: prefill cost per token grows ~linearly with depth (0.1 s at d0, ~0.4 s at 16K). Extrapolated: fill 128K ~2 days, fill 1M ~3-4 months; decode at 1M depth ~0.05 t/s. Cause: llama.cpp runs full MLA attention (DSA sparse indexer not implemented). Practical usable context: tens of K tokens, maybe ~64K for one-off overnight jobs. Flash-Next is the long-context candidate.

## Not yet measured
KV bytes per token (not printed by llama-bench; needs a llama-server run), depth 32K and beyond, MTP, concurrency, prompt cache, max-context proof, hybrid GPU, ik_llama.cpp and other forks.
