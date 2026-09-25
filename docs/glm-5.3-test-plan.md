# GLM-5.3 (full) on jarvis-1: test plan for context size and speed

Written 2026-09-25 by Claude for Simon. Sources: the memory pages in docs/wiki/ (big-model-decode-prefill, cpu-moe-speed-levers, cpu-moe-hardware-anchors, context-and-speed-per-model, prompt-cache-and-prefill-reuse, system-performance-levers, glm-5.3-quant-quality, jarvis-speed-tuning) plus a web check on 2026-09-25.
Labels: MEASURED (on this box), SOURCE (read in llama.cpp code or docs by an earlier session), ESTIMATE (arithmetic or other people's hardware), VERIFY (not checked yet).

## The setup being tested
- Model: unsloth GLM-5.3 UD-Q4_K_XL, 11 shards, 468 GB / 435 GiB, copied to /home/simon/models/GLM-5.3 on the 990 PRO. 753B total, 40B active, 78 layers, MLA attention (kv_lora_rank 512).
- Quality at this quant: 94.29% top-1 vs full precision, mean KLD 0.037 (Unsloth table). Going lower to save RAM costs a lot: UD-IQ3_XXS is 84.15%.
- Runtime: stock llama.cpp in ~/llama.cpp (supports glm-dsa). Test server = ~/glm-test.sh, a transient unit glm-test on 172.17.0.1:8082, GPUs hidden, MemoryMax 465G, no swap, OOMScoreAdjust 1000.
- Jarvis keeps running on the GPUs and socket 0 unless a phase says otherwise.

## What limits context on this model (and what does not)
1. RAM is probably NOT the limit. llama.cpp stores MLA models as a compressed K cache only (no V cache): about (512 + 64) x 2 bytes x 78 layers = ~88 KiB per token at f16 [SOURCE: src/llama-kv-cache.cpp is_mla / has_v]. With ~30 GiB left under the 465G cap after weights, that is ~350K tokens on paper [ESTIMATE]. Confirm from the startup log line that reports the KV buffer size (MiB) divided by -c.
2. The DSA sparse "lightning indexer" is NOT implemented in llama.cpp. The indexer tensors load but are unused, and the model runs as full MLA attention [SOURCE: llama.cpp issue #20363; web check 2026-09-25]. So attention cost grows with context instead of staying near-flat as the model was designed.
3. PREFILL SPEED is the real limit. Comparable hardware (2x E5-2696 v4, DDR4-2400) measured 14-16 t/s prompt processing on a GLM-class MoE with ik_llama.cpp, ~44 t/s with --split-mode graph [SOURCE: ubergarm GLM-4.7 discussion #5]. Expect lower here. At 15 t/s a 32K prompt takes ~35 minutes. So "more context" in practice means: faster prefill, and never prefilling the same text twice.

## Speed expectations before tuning
- Decode is bandwidth-bound: ~24.8 GB read per token. MEASURED STREAM on this box: 29.5 GB/s one socket, 59.5 GB/s both sockets interleaved (after the uncore/governor fix). Realistic llama.cpp conversion is lower.
- ESTIMATE: 1.5-2.5 t/s decode untuned on stock llama.cpp, 2.5-4 t/s with the levers below, ceiling ~5.

## Phase 1: Jarvis stays up, stock llama.cpp, CPU only (no downtime, no builds)
| # | Test | How | What it decides |
|---|------|-----|-----------------|
| 1a | Does the GGUF carry an MTP head? | Read tensor names with gguf-py; look for blk.78.nextn.eh_proj.weight | If present, MTP is available on mainline (glm-dsa MTP graph exists) for a possible ~1.3-1.6x decode [ESTIMATE] |
| 1b | Real KV cost per token | First load at -c 32768; read the KV size line in the log | Confirms ~88 KiB/token and so the real context ceiling |
| 1c | Baseline decode and prefill | llama-server at 32K, one 2K-token prompt, 200-token answer; read the timings | The number every later lever is compared against |
| 1d | Threads | llama-bench -t 32,36 (decode) and --threads-batch 36,72 (prefill) | Notes say physical cores for decode, hyperthreads help prefill [SOURCE: ubergarm run; STREAM on this box showed 72 threads add nothing to bandwidth] |
| 1e | Batch sizes for prefill | llama-bench -b/-ub 512, 2048, 4096 on a 4K prompt | Up to ~2x prefill claimed [SOURCE: llama.cpp discussion #23262] |
| 1f | Flash attention on CPU | llama-bench -fa 0 vs 1 at depth 8K | Needed for a quantized cache; may also change long-context speed. VERIFY that the MLA path accepts it |
| 1g | K cache q8_0 vs f16 | llama-bench -ctk q8_0 vs f16 at depth 0 and 16K | Halves the cache (2x context). On the 27B's GPUs q8_0 caused a big slowdown at depth; on CPU it is unmeasured. Keep f16 unless q8_0 is flat |
| 1h | Prompt cache across turns | Server with -lv 4 and --cache-reuse 256; send the same long prompt twice | Second turn should skip the prefill. MLA with no recurrent state should cache normally (low risk), but the log line "forcing full prompt re-processing" is silent at default verbosity |
| 1i | Save/restore a long context | --slot-save-path ~/glm-slots; prefill a big document once, save the slot, restart, restore | Turns a 30+ minute prefill into a load from NVMe. The file has no model-identity check, so only restore into the same model and flags |

## Phase 2: needs a Jarvis downtime window (Simon's decision; ~1-2 h)
| # | Test | Why it needs downtime |
|---|------|-----------------------|
| 2a | numactl --interleave=all instead of --preferred=1 | Interleaving puts ~218 GiB on node 0, where Jarvis is memory-bound. MEASURED on this box: interleaved STREAM is 2.01x one socket. The biggest free lever for a model that must span both sockets |
| 2b | GPU hybrid: -ngl 99 with -cmoe (all experts on CPU), then walk -ncmoe N down | Attention, shared tensors and the KV cache go to the V100s, experts stay in RAM. ~1.3x decode [ESTIMATE], and the KV cache leaves system RAM. Needs both GPUs free |
| 2c | MTP draft (only if 1a found the head) | --spec-type draft-mtp, sweep --spec-draft-n-max 2-5. MoE verification reads the union of experts; routing correlation keeps that sub-linear [SOURCE: Cohere, ~2.5x experts at K=3 not 3.6x]. Can also run CPU-only in phase 1 if RAM allows |

## Phase 3: a second engine build (no downtime; separate build tree, production binary untouched)
- ik_llama.cpp supports GLM-5 (PR 1268) [SOURCE: README]. Measured on comparable AVX2 Xeons: 1.5-1.9x decode, ~1.9x prompt processing vs mainline [SOURCE: discussion #164].
- Flags worth testing there: --run-time-repack (lossless repack of the same Q4 bits, needs --no-mmap, VERIFY support for Unsloth UD mixed quants: works on some commits, regressed after 68a5b604 per GH #271), --split-mode graph (the ~3x prefill in the ubergarm run), --threads 36 --threads-batch 72, --merge-qkv.
- NUMA mirroring is NOT possible for GLM-5.3 at Q4 (2 x 435 GiB > 503 GiB).

## Also worth knowing
- Concurrency beats single-stream: several requests at once share the expert reads, so aggregate throughput rises much faster than per-request speed falls [SOURCE: big-model-decode-prefill]. Best use of GLM-5.3 is queued background jobs, not interactive chat. Sweep --parallel 1/2/4 and compare aggregate t/s.
- GLM-5.3-Flash would be ~2x faster (18B active) and fits one socket, but needs the Unsloth fork (glm5next is not in this build). Qwen3.8-Flash-Next is ~6-10x faster than GLM-5.3 and runs on this build today.

## Order
1a now (read-only on the drive), then 1b-1c on first load, then 1d-1g with llama-bench, then 1h-1i. Only then decide on a phase 2 window.
