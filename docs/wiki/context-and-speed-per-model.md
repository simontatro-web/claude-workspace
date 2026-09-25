# context-and-speed-per-model

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 23, 2026).
> Cowork-only links kept as page names.
>
> Summary: Per-model context-window and decode-speed estimates for every model on Jack's jarvis-1 shortlist (Sep 23 2026) — RAM headroom after weights, KV cost per token, usable context, and t/s. Read before choosing a model for a long-context or agentic task, or before promising a context size.

Companions: model-tier-ceiling (why the tiers are what they are), cpu-moe-speed-levers (the speed arithmetic), qwen38-flash-next, mimo-v2.6-feasibility. THE GOVERNING FRAME: usable context is capped by RAM LEFT OVER AFTER WEIGHTS, not by the model's advertised native context. Every model here advertises 256K-1M. Almost none of them can actually hold it on this box. Hardware: 503 GiB RAM, ~251 GiB/socket, 2x V100 16GB, measured ~39 GB/s effective memory bandwidth.

## THE TABLE (decode t/s and usable context; MEASURED items marked, everything else is arithmetic)

| Model | Weights | RAM/VRAM left | Native ctx | KV per token | Usable ctx | Est. decode t/s | | Qwen3.8-27B Q4_K_M, 2 cards (CURRENT) | 17.66 GiB VRAM | ~12 GiB | 256K | q8_0 ~35 KiB (only 16 of 64 layers keep KV) | ~300K+ | 28.09 MEASURED; 83 MEASURED w/ MTP | | Qwen3.8-27B Q3_K_M+MTP, 1 card (PROPOSED) | 12.57 GiB VRAM | ~2.3 GiB | 256K | same | ~32-64K | ~47 (anchor: 47.3 measured on 2x V100-SXM2, GSQ-RCO IQ3_S-mtp) | | Qwen3.8-Flash-Next UD-Q4_K_XL | 103.7 GiB | ~399 GiB | 262K (1M w/ YaRN) | QSA, 2048-token budget at 4:1 — very light, UNMEASURED | not RAM-limited; full 262K plausible | 10.5 raw / 14-17 mirrored / 18-27 +MTP | | GLM-5.3-Flash UD-Q4_K_XL | 186 GiB | ~317 GiB | 1M | KDA hybrid linear — tiny, UNMEASURED | large, but OOM reported at ~32k in the fork | 3.5 raw / ~5-7 mirrored (MTP not wired) | | GLM-5.3 full UD-Q4_K_XL | 435 GiB | ~68 GiB | 1M | SEE THE 40x FORK BELOW | ~19K to ~813K — MUST MEASURE | 1.6 raw / 2.5-4 optimized | | Hy4-preview UD-IQ1_M | 219.2 GiB | ~284 GiB | 1M | UNMEASURED | large | 2.6 raw / ~4.2 mirrored | | Hy4-preview Q4_K_M | 435.2 GiB | ~68 GiB | 1M | UNMEASURED | small | ~1.3 — slowest of the set | | MiMo-V2.6-Pro | ~498 GiB | ~5 GiB | 1M | 350 KiB/token f16 (plain-GQA upper bound: 8 kv heads x (192 K + 128 V) x 2B x 70 layers) | ~15K at f16, ~30K at q8_0 | ~1.8 raw / ~3.3 w/ GPU attention |

## *** THE BIGGEST OPEN QUESTION: GLM-5.3'S KV CACHE COULD BE 40x EITHER WAY ***

Pulled zai-org/GLM-5.3/config.json live Sep 23 2026: 78 layers, 64 attention heads, num_key_value_heads: 64 (NO GQA — full MHA), head_dim: 192, hidden_size 6144, max_position_embeddings 1,048,576. It ALSO has kv_lora_rank: 512 (MLA-style compressed KV, DeepSeek-lineage) and indexer_types alternating "full"/"shared" (the DSA sparse indexer). 256 routed experts, 8 per token, dense layers 1-3 then MoE 3-78. rope theta 8,000,000. TWO POSSIBLE llama.cpp PATHS, and nobody has checked which one glm-dsa actually takes:

- (A) Full dense MHA fallback (what cpu-moe-speed-levers concluded, since the DSA indexer is NOT implemented — issue #20363, POC only, "horribly slow"): 64 kv_heads x 192 head_dim x 2 (K+V) x 2 bytes x 78 layers = 3,833,856 B = 3.66 MiB PER TOKEN at f16. Against 68 GiB headroom that is ~19,000 tokens, or ~38,000 at q8_0 KV.
- (B) MLA compressed path (if llama.cpp uses kv_lora_rank the way it does for DeepSeek): ≈ (512 + 64 rope) x 2 bytes x 78 layers = ~87.75 KiB per token. Against 68 GiB that is ~813,000 tokens — effectively the full 1M. That is a 40x spread between "barely fits a long file" and "the whole million". It is the single most valuable thing to measure on first load, and it decides whether GLM-5.3 is usable for agentic work at all. HOW TO SETTLE IT IN ONE COMMAND: load with a known -c and read llama.cpp's own KV-cache allocation line in the startup log (it prints KV self size in MiB), then divide by the context length. Do this before planning any long-context task around GLM-5.3.

## *** THE CAVEAT THAT MATTERS MORE THAN ANY NUMBER ABOVE: ALLOCATABLE CONTEXT IS NOT USABLE CONTEXT ***

On a CPU MoE, prefill is compute-bound, not bandwidth-bound, and Jack's Haswell has AVX2 but no AVX-512. Filling a large context costs real wall-clock BEFORE the first token appears. The arithmetic to apply: at 50 t/s prefill a 100K prompt is 33 minutes; at 10 t/s it is 2.8 hours. No prefill number has been measured on his box for any of these models — measure prefill before decode, because it is the thing that will actually make a big context unusable. Related, already on file: llama.cpp issue #22967 (Gated DeltaNet CUDA prefill is token-sequential, chunked PR #26001 unmerged) means do not expect the V100s to rescue prefill on Flash-Next; the CPU reference path already has the chunked algorithm, so run it CPU-heavy. -b 4096 -ub 4096 is a free prefill-only lever worth ~2x.

## PROMPT-CACHE RISK CHANGES THE PRACTICAL CONTEXT TOO

If KV reuse across turns breaks, every turn reprocesses the whole prefix and effective context collapses. Risk by architecture (cpu-moe-speed-levers): GLM-5.3-Flash (KDA hybrid) HIGH; Qwen3.8-Flash-Next (Gated DeltaNet recurrent) HIGH, UNTESTED; MiMo (hybrid SWA, sliding_window 128) HIGH; GLM-5.3 full (dense fallback) LOW — the dense fallback that wrecks its KV size is the same thing that makes its caching reliable. Detect with -lv 4 and the line "forcing full prompt re-processing due to lack of cache data" (silent at default verbosity).

## ONE-LINE SUMMARY PER MODEL, for picking

- Qwen3.8-27B (2 cards): 83 t/s measured, ~300K ctx. Best all-round today. The 1-card re-layout trades ctx down to ~32-64K for a free GPU.
- Flash-Next: the only model with BOTH big usable context and non-trivial speed. ~18-27 t/s, 262K.
- GLM-5.3 full: highest ceiling he can run, but context is 19K-813K unknown and 2.5-4 t/s. Measure KV first.
- MiMo: highest index (46) and the worst context on the box, ~15-30K, because weights eat 498 of 503 GiB.
- Hy4 IQ1_M: fine headroom, ~4 t/s, but an unmeasured 2.45 bpw quant.
- GLM-5.3-Flash: no lane (see model-tier-ceiling).

## *** HOW TO INCREASE CONTEXT — researched Sep 23 2026. Ranked by value. Jack's "anything that runs" makes the fork tier available. ***

### TIER 1 — free, stock build, do these first

- KV QUANTIZATION: --cache-type-k q8_0 --cache-type-v q8_0 → 2x context. q4_0 → 4x. *** THE GOTCHA THAT SILENTLY HALVES IT: llama.cpp errors "V cache quantization requires flash_attn". *** K-cache quantizes without FA; V-cache does not. So without flash attention you only get half the saving. On CPU-resident models llama.cpp's CPU FA path is fine. On Jack's Volta GPUs FA is the problem — see Tier 2.
- -fa flash attention — prerequisite for the above, and it also removes the big attention workspace. orchestrator-slot-plan already records that FA being compiled out is what makes the 27B's CLIP graph materialize a 4.27 GiB matrix.
- *** MOVE THE KV CACHE TO VRAM WHILE EXPERTS STAY IN RAM: -ngl 99 -ot "ffn_.*_exps.*=CPU" *** — attention layers (and their KV) go to GPU, giant expert FFN stays on CPU. This is transformative for MiMo specifically, whose RAM headroom is only ~5 GiB while up to 32 GiB of VRAM sits idle. MiMo at 350 KiB/token: 5 GiB RAM = 15K tokens → 16 GiB VRAM (one freed card) = ~48K tokens, and ~96K with q8_0 KV.
- Smaller weight quant — the blunt lever. Every GiB off the weights is a GiB of KV. Hy4 Q4_K_M (435 GiB, 68 GiB left) vs UD-IQ1_M (219 GiB, 284 GiB left) is a 4x context difference on the same model.
- -b 4096 -ub 4096 — prefill-only, ~2x, free. Does not raise the ceiling but makes a big context reachable in acceptable wall-clock.

### TIER 2 — V100-SPECIFIC FORKS. These exist, they are active, and they target exactly Jack's hardware.

- *** fishlikeX/sm70-attn — THE MOST RELEVANT REPOSITORY FOUND THIS PASS. *** "FlashAttention brought back to Tesla V100." Adds SM 7.0 D256 kernels, SplitKV3 (three-way KV splitting for long contexts, +3.7% at 176k), q4_0 KV cache with optional in-kernel direct read (~470 MB VRAM saved), and DFlash2 speculative decoding with multimodal fixes. Base: llama.cpp commit 25ae3a9b3 (Aug 2026), 11,145 commits, actively maintained (recent fixes for "context contamination" and multimodal crashes). MEASURED: 176k prefill 521.93 t/s vs stock 372.94 t/s = +39.9% (same-session A/B). Decode unchanged (~29 t/s) because decode is weight-bandwidth-bound, not attention-bound — which is the correct and honest framing. Limits: sm_70 only, head_dim=256, falls back to stock paths for non-causal masks / small batches; q4_0 direct-read costs ~4% prefill for the memory saving. WHY IT MATTERS: it unlocks quantized V-cache on his GPUs, which is the thing Tier 1 item 1 is blocked on.
- llama.cpp PR #28887 "CUDA: enable sparse FlashAttention on Volta" (CoREse) — the mainline route to the same capability. Check merge status before building a fork.
- jackjusko/jusko-llama-volta-qwen3flash — targets SM70/SM75, "main target is long-context Qwen3.8-27B serving" despite the repo name. Claims 262,144 tokens with q8_0 K/V on a single V100, block-first QSA selection, quantized-weight reuse during prefill, tensor-core attention for q8_0 K/V, MTP with deferred prompt catch-up, and "recurrent state checkpointing for cached agent turns" — aimed squarely at the prompt-cache-breakage risk. Measured at 100K cached tokens: 128-token append +22.49%, 1000-token append +43.94% (3.323s → 2.308s), decode +32.19%. Tracks upstream 465e49b9c. TREAT WITH CAUTION: validated on a V100-SXM2 32 GB, NOT Jack's V100-PCIE-16GB, and it has 2 stars / 1 fork. Minimal independent validation.
- Encoded404/beellama-QoL-v100.cpp — "better V100 performance... KVarN, KV cache precision tail, low-bit quants for longer context or better precision in the same VRAM."
- ik_llama.cpp issue #2463 "Volta sm_70 support" — check before assuming the ik engine lever applies to GPU-resident work.

### TIER 3 — TURBOQUANT: the biggest KV compression available, experimental

llama.cpp discussion #20969. Randomized Hadamard Transform (WHT + deterministic sign flips) then 3-bit Lloyd-Max optimal scalar quantization, after Google Research.

- TQ3 = 4.9x vs FP16; TQ4 = 3.8x. Roughly 2x better than q8_0.
- Flags: --cache-type-k turbo3 --cache-type-v turbo3
- Quality: +1-2% PPL at 3-bit on larger models — cheap for the compression.
- Cost: 10-35% generation slowdown; works best on 3B+ models; FA recommended.
- NOT MERGED. Multiple independent implementations: TheTom's Metal fork, CUDA ports by spiritbuun and Madreag, CPU-only implementations, Vulkan in development. The CPU-only ones matter here because the giants are CPU-resident.

### TIER 4 — beyond native context

YaRN rope scaling. Flash-Next is explicitly documented as 262,144 native, extensible to 1,000,000 via YaRN. Costs quality at the extremes; only reach for it when the model is otherwise fine.

### WHAT THE STACK BUYS, worked through

| Model | Baseline | +q8_0 KV | +q4_0 KV | +TQ3 | +KV on GPU | | GLM-5.3 (dense-MHA case) 3.66 MiB/tok, 68 GiB | 19K | 38K | 76K | ~93K | n/a (too big to offload attention cheaply) | | GLM-5.3 (MLA case) 88 KiB/tok | 813K | — | — | — | already fine | | MiMo 350 KiB/tok, 5 GiB RAM | 15K | 30K | 60K | 74K | 48K on 16 GiB VRAM, ~96K +q8_0, ~230K +TQ3 | HONEST FRAMING: none of this fixes prefill. Raising the ceiling to 93K does not help if filling 93K takes three hours. sm70-attn's +39.9% prefill is the only lever found that attacks prefill directly, and it only applies to GPU-resident attention.

## *** Sep 23 2026 — BLIND VERIFICATION PASS. ACCURACY 80.3%, BELOW JACK'S 95% BAR. THREE CORRECTIONS, TWO OF THEM CHANGE PLANS. ***

Independent auditor, told to treat this file as untrusted, checked every claim against live config.json files, the HF API byte counts, and llama.cpp master source. Arithmetic scored 100% — every one of ~14 recomputations reproduced exactly, and there is NO GB/GiB error anywhere in this file. The failures are all architectural inference and third-party capability claims. Verdict worth keeping: "an excellent transcriber and calculator, and an unreliable inferrer. Trust its numbers; re-derive its conclusions."

### *** CORRECTION 1 — MiMo-V2.6-Pro DOES NOT FIT ON THIS BOX AT ALL. THE "~498 GiB / ~5 GiB LEFT" ROW IS WRONG. ***

The only MiMo-V2.6-Pro GGUF in existence is kernelpool/MiMo-V2.6-Pro-RL-MXFP4-GGUF: part1 480,000,000,000 B + part2 77,146,510,560 B = 557,146,510,560 B = 518.88 GiB. Against 503 GiB of RAM that is −15.9 GiB. It cannot be loaded. (Other search hits are MiMo Flash, not Pro. No Unsloth Pro GGUF exists.) EVERY MiMo CELL IN THIS FILE IS VOID: the ~5 GiB headroom, the 15K/30K usable context, the 48K/96K/230K -ot lever row, and the "highest index (46) and the worst context on the box" verdict. The correct verdict is "does not load", not "tight". CONSEQUENCE FOR model-download-manifest: the 573.5 GB MiMo source download has no payoff at Pro scale unless RAM grows past ~520 GiB. Re-decide before spending the trip on it. Separately, and the note was silent on it: llama.cpp PR #29257 (AesSedai) MERGED Sep 22 2026 — MiMo-V2.6 Pro and Flash convert and load with vision and no runtime changes. So the architecture is no longer the blocker; RAM is.

### *** CORRECTION 2 — THE "40x KV QUESTION" FOR GLM-5.3 IS LARGELY SETTLED, AND THE ANSWER IS CASE B (~813K). ***

The root error: reading num_key_value_heads: 64 as "NO GQA — full MHA". The same config.json carries kv_lora_rank: 512, q_lora_rank: 2048, qk_rope_head_dim: 64, qk_nope_head_dim: 192, v_head_dim: 256 and architectures: ["GlmMoeDsaForCausalLM"]. In MLA configs num_key_value_heads == num_attention_heads is a vestigial field, not evidence of MHA. DECISIVE, FROM llama.cpp MASTER SOURCE: src/llama-kv-cache.cpp contains const bool is_mla = hparams.is_mla(); const bool has_v = !is_mla; — for MLA models llama.cpp allocates NO V CACHE AT ALL and caches K over n_layers × (kv_lora_rank + qk_rope_head_dim). That is exactly case B: 87.75 KiB/token → ~813,000 tokens at 68 GiB. Cross-checked against HF's kv-cache-calculator space, which uses the same formula. The stated reason for entertaining case A was a non-sequitur: issue #20363 (DSA indexer POC-only, "horribly slow") concerns the sparse indexer, which is orthogonal to the KV layout. Indexer unimplemented means dense attention COMPUTE over the MLA latent, not an expanded KV cache. So plan GLM-5.3 around ~813K tokens, not "19K-813K unknown". Still read the startup KV line on first load as confirmation, but this is no longer the open question this file called "the single most valuable thing to measure." Also: even the fictional case A was miscomputed. A genuine dense expansion caches qk_head_dim 256 and v_head_dim 256, not 192/192: 64 × (256+256) × 2 × 78 = 4.875 MiB/token → 14,283 tokens, not 3.66 MiB / 19,045.

### CORRECTION 3 — sm70-attn's V-CACHE CLAIM, AND WHY OUR OWN MEASUREMENT OVERRIDES THE AUDIT

The auditor flagged as WRONG this file's claim that sm70-attn "unlocks quantized V-cache", noting the README's usage line is -ctk q4_0 -ctv f16 (quantized K, f16 V). *** BUT WE MEASURED OTHERWISE ON Sep 23 2026. *** Built the fork with -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=70; configure reported FlashAttention K-V type combinations: f16-f16;q4_0-q4_0;q8_0-q8_0;bf16-bf16, and a server run with -ctk q8_0 -ctv q8_0 -c 65536 loaded and generated normally (59.25 t/s, 3500 tokens). Quantized V cache demonstrably works on this build. The auditor inferred from a README example; we ran it. Keep the capability claim, drop the overstatement that it was the unique reason to use the fork. VALID part of the audit: the fast path is PREFILL-ONLY and needs batch >=256 (confirmed in our own logs: [sm70-d256] REJECT: no mask or small batch on every 2-token warmup call). It cannot help decode-time KV pressure. Also the compiled KV combos are matched PAIRS — -ctk q4_0 -ctv f16 is mixed and not in the compiled set, so the README's own example may fall back.

### SMALLER CORRECTIONS

- The llama.cpp error string quoted here is wrong and a grep for it will fail. Actual text: "quantized V cache was requested, but this requires Flash Attention". And it throws and refuses to start — it does NOT "silently give you half the saving".
- indexer_types is not "alternating". Real pattern: three full, then a period-4 repeat of shared,shared,shared,full.
- MiMo's 350 KiB/token is a worst case presented as the operating figure. This file records sliding_window: 128 separately and never reconciles the two: most MiMo layers are SWA-128 and cache 128 tokens, not full context. Moot now (Correction 1) but the same reasoning flaw will recur on the next hybrid-SWA model.
- TurboQuant: "FA recommended" should read FA REQUIRED for acceptable decode, and the "10-35% slowdown" band holds only at long context on one backend (measured +0.7% @6K, -11.9% @24K, -36.8% @110K; Metal/CUDA/CPU forks report near-parity). The turbo3 flag spelling is UNCONFIRMED — the visible implementation (AmesianX/TurboQuant, now archived) uses tbq3/tbqp3/tbq4.
- PR #28887 is CLOSED, not pending (closed for an AI-usage-policy violation on the description, not on technical grounds), and it only ever supported head_dim 512 for DeepSeek-V4 sparse attention — irrelevant to Qwen's 256. There is no mainline route to Volta flash attention.
- Hy4 IQ1_M at 2.45 bpw, all five weight sizes in GiB, the headroom subtractions, and the #22967/#26001/#20363 issue tracking all CONFIRMED exact.

## *** Sep 23 2026 (later) — CORRECTION 1 ABOVE IS ITSELF SUPERSEDED. "MiMo DOES NOT LOAD" IS WRONG. READ mimo-v2.6-feasibility BEFORE QUOTING IT. ***

Correction 1 concluded 518.88 GiB of weights against 503 GiB RAM = "cannot be loaded". That is true only for a naive full-RAM load. mimo-v2.6-feasibility (updated the same day, later) establishes the fit:

- -ngl 99 -ot "ffn_.*_exps.*=CPU" puts the mxfp4 experts (~465.8 GiB) in RAM and ~30 GiB of non-expert tensors on the two V100s → RAM ~489 GiB against 503. It fits, resident, no paging. Requires the 27B stopped.
- Even unaided it still runs: llama.cpp mmaps by default, so a ~16 GiB overflow (~3% of the model) pages from NVMe rather than failing. NEVER --mlock in that state — it converts a graceful slowdown into an OOM kill. I stated "does not load" to Jack twice on Sep 23 while this correction was already on file. The lesson: Correction 1's flat verdict must not be quoted without checking the MiMo file, which is the authority on it. The verdict that survives is the USE-CASE one, not the fit one: ~2-5 t/s, ask-one-hard-question model, prefill unmeasured.
