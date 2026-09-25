# Every speed lever for the big CPU models on jarvis-1 (master list)

Written 2026-09-25 after Simon asked to speed the models up "in ANY and EVERY possible way" without giving up much quality. Covers Qwen3.8-Flash-Next first (the likely big-model slot), GLM-5.3 and GLM-5.3-Flash where different.
Labels: MEASURED (on this box), SOURCE (code/docs/others' hardware), ESTIMATE, VERIFY. Gains multiply only roughly; never quote a stacked number as measured.

## Why these models are slow here (the frame)
Decode is memory-bandwidth-bound: t/s = effective bandwidth / bytes read per token.
- Memory: 16 x 32 GB dual-rank RDIMM, 2 per channel, running 1866 MT/s (rated 2133; 2 DIMMs per channel forces 1866). 59.7 GB/s theoretical per socket. STREAM Triad MEASURED 29.5 GB/s one socket, 59.5 GB/s both interleaved.
- Flash-Next baseline MEASURED: 4.10 t/s decode, 29.35 t/s prefill (pp512), socket 1 only, 18 threads. ~15 GB/s effective if ~3.7 GB/token: about half of socket STREAM. GLM-5.3 reached ~62% of STREAM, so Flash-Next's small experts (512 experts, 10 active) are likely less efficient per byte in stock llama.cpp. That is exactly what fused-MoE kernels (ik_llama.cpp) target.
So the levers are: (1) more bandwidth, (2) fewer bytes per token, (3) better kernels, (4) fewer tokens needed per answer, (5) more answers per pass.

## Levers, ranked by expected gain per effort
| # | Lever | Expected gain | Quality cost | Cost / risk | Status |
|---|---|---|---|---|---|
| 1 | Both sockets (interleave) instead of socket 1 only | ~1.6-1.9x decode (STREAM 2.0x; GLM got 1.35-1.65x) | none | Needs Jarvis off in the current rule. NEW IDEA: Jarvis's 27B runs on the GPUs, so test interleave WITH Jarvis running and measure both. If Jarvis barely slows, this is the biggest free always-on lever | MEASURED 2026-09-25 beside Jarvis: decode 5.60 (+28% vs socket 1), prefill 50.66 (+60%); Jarvis -3% median, -15% worst probe. Earlier note: beside-Jarvis interleave test WRITTEN: ~/bench/il-beside.py (98 lines, 4946 B, 95e32f924b835a10), Simon approved; runs after the MTP test |
| 2 | ik_llama.cpp (fused MoE -fmoe, -rtr run-time repack, better AVX2 kernels, -ser, --split-mode graph for prefill) | 1.5-1.9x decode, ~1.9x prefill on similar AVX2 Xeons (SOURCE ik discussion #164; other models) | none (same weights) | separate build; qwen4exp SUPPORTED in ik (MEASURED 2026-09-25: LLM_ARCH_QWEN4EXP, build_qwen4exp, also in llama-spec-features.cpp and llama-delta-net.h) | cloned ~/ik_llama.cpp at 1aaf7105 (2026-09-25), 214M; flags present: -rtr/--run-time-repack, -mla, -amb, -ser, --numa, -sm/--split-mode fused MoE is ON by default (-no-fmoe disables); has -fdn/--fused-delta-net (fused Gated DeltaNet: 3 of every 4 Flash-Next layers, prefill lever, default VERIFY); qwen4exp NextN/MTP code in llama-spec-features.cpp handles a NextN block in a companion file (so ik may run the Flash-Next MTP heads: VERIFY flags); --numa has only distribute/isolate/numactl (NO mirror in this commit: mirroring needs ik PR #2396 or another fork); examples include sweep-bench, spec-bench, batched-bench. Not built |
| 3 | MTP speculative decoding (PR #28243 build) | 1.3-1.7x at 1 request (vendor 1.67x on GPU; CPU unmeasured) | none if output identical (checked by the harness) | PR unmerged, known bugs at n-max >= 3 | MEASURED 2026-09-25: 1.57x mean at shared-Q8 n-max 3 (4.30 -> 6.73 t/s, 7.62 on reasoning) on socket 1; outputs deterministic, differ from MTP-off at a near-tie token; quality-suite check pending |
| 4 | NUMA mirroring (a full copy on each socket; llama.cpp PR #27986, ik PR #2396, vproxy fork) | ~1.5x over interleave (SOURCE 1.47-1.63x on other MoEs) | none | fork build; needs 2 x 104 GiB RAM, so no big second model at the same time | not built |
| 5 | Smaller quant: GSQ-RCO IQ3_XXS (75.8 GB, vendor "99.4% of base") or Q2_0 (66.4 GB) | up to ~1.3-1.5x decode (fewer bytes) IF the IQ kernels are fast on AVX2 (often they are slower than K-quants: VERIFY) | small to moderate: measure KL divergence and top-1 vs UD-Q4_K_XL | files already on the drive | not tested |
| 6 | Control reasoning length (reasoning effort / thinking budget) | Flash-Next is "very verbose" (SOURCE AA): halving thinking tokens halves time-to-answer | some, task-dependent: measure on the quality suite | prompt/template setting | not tested |
| 7 | Prompt cache reuse + slot save/restore | removes repeated prefill entirely on multi-turn and repeated documents | none | Gated DeltaNet is HIGH RISK for forced re-processing (-lv 4 test) | harness not written |
| 8 | Concurrency (--parallel 2/4/8) for background jobs | aggregate throughput several x (expert reads shared) | none | per-request speed drops; MTP loses at 8 | harness not written |
| 9 | n-gram / lookup speculation (stock --spec-type ngram-*) for copy-heavy work (code edits, rewriting) | large on copy-heavy text, ~none on fresh prose | none | stock build | not tested |
| 10 | Hybrid GPU: attention + shared expert + hot experts on a V100 | ~1.2-1.5x decode (ESTIMATE); prefill help limited (Gated DeltaNet CUDA prefill is token-sequential, llama.cpp issue #22967) | none | needs a free V100: only after the 27B single-card A/B frees one, or in Jarvis-off windows | not tested |
| 11 | Transparent huge pages "always" during runs (THP is madvise now) | ~0-10% (fewer TLB misses on random expert reads) (ESTIMATE) | none | one sysctl, reversible | not tested |
| 12 | Batch / ubatch, threads, flash attention, K/V cache type, poll | small; finds the best flags | none / small (q8_0 cache) | none | RUNNING today (fn-a1..a7) |
| 13 | Compiler: GGML_NATIVE already on; try clang, -O3, LTO | ~0-5% | none | rebuild in a separate tree | not tested |
| 14 | Expert pruning (REAP) | ~1.2-1.3x (25% fewer experts) | real, unverified | no Flash-Next REAP GGUF known | watch |

## Hardware levers (Simon's money; none bought)
- Memory speed: 2 DIMMs per channel of dual-rank RDIMM caps at 1866. Quad-rank LRDIMM can run 2133 at 2 per channel on E5 v3 (SOURCE Supermicro table, per the system-performance-levers page): ~+14% bandwidth, and a path to more RAM. VERIFY for this board before buying.
- CPU: 2x E5-2699 v4 / 2696 v4 (Broadwell, same socket; used prices low). Supports DDR4-2400 at 1 DIMM per channel, and slightly better memory controllers; board support needs a BIOS check (VERIFY). Gain modest at 2 per channel.
- GPU/VRAM: more VRAM lets more of the model sit on GPUs (see gpu-upgrade-options). Power is near the 120 V household limit already (SOURCE power page).

## GLM-5.3 and GLM-5.3-Flash specifics
- GLM-5.3: interleave MEASURED 1.35-1.65x; hybrid GPU (-ngl 99 -ncmoe 79 first); ik_llama.cpp; MTP head present (stock draft-mtp VERIFY for glm-dsa); mirroring impossible at Q4 (870 GiB). Prefill at depth is the wall: only the DSA indexer (not in llama.cpp) fixes that.
- GLM-5.3-Flash: needs the Unsloth fork; mirroring possible at Q4 (2 x 186 GiB); MTP only in unmerged ik PRs.

## Order recommended
1. Finish today's flag sweep (running), then the MTP test.
2. Interleave-beside-Jarvis test (new): the cheapest possible big win if Jarvis is unaffected.
3. ik_llama.cpp build and head-to-head (check qwen4exp support first).
4. GSQ-RCO quants from the drive, with KL divergence.
5. Mirror fork. 6. Reasoning-length and prompt-cache tests in the server harness. 7. Stack the winners and measure the stack once.
