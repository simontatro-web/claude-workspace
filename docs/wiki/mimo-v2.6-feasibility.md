# mimo-v2.6-feasibility

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 23, 2026).
> Cowork-only links kept as page names.
>
> Summary: Whether Jack can run MiMo-V2.6-Pro (the top-scoring open-weights model) on jarvis-1 — live architecture/size/config data pulled Sep 22 2026, the llama.cpp support change that landed that day, the VERIFIED mxfp4-on-Volta answer, and the RAM and conversion blockers. Read before any MiMo work or before buying hardware for it.

Supersedes the "no GGUF exists, not a real option" line in local-model-landscape and glm-5.3-quant-quality. Related: cpu-moe-speed-levers (speed arithmetic), model-storage-plan (where it would live). Everything below marked VERIFIED survived an adversarial blind-agent check against llama.cpp master source and the HF API on Sep 22 2026. That check scored the first draft of this file 80% and corrected three things; the corrections are folded in and the original errors are flagged so they are not reintroduced.

## STATUS CHANGED Sep 22 2026 — ARCHITECTURE SUPPORT MERGED [VERIFIED]

ggml-org/llama.cpp PR #29257 "convert: add MiMo-V2.6 support" (AesSedai) MERGED Sep 22 2026. Covers both Pro and Flash (PR text: "This PR adds conversion support for MiMo-V2.6 Pro and Flash. Both of these models use mxfp4 experts like DSv4 and Kimi-K3 do, so I hoisted the K3 repack to base.py"). CORRECTION to an earlier claim: it is NOT strictly "conversion-only." The diff touches four files: conversion/base.py (+30), conversion/kimi_k3.py (-30), conversion/mimo.py (+84/-1), and common/chat.cpp (+2) — a chat-template fix excluding these models from the Qwen3-Coder XML tool-call template. No src/llama-model.cpp, src/llama-arch.cpp or ggml/ changes, so the spirit (no runtime architecture work needed) holds and mainline can run it once converted. ggerganov had flagged the tool-call template bug; fixed via autoparser in commit 12ff7a0.

## *** THE MXFP4 GATE IS CLEARED — BOTH CUDA AND CPU. [VERIFIED AGAINST SOURCE] ***

This was the single unknown that could have killed the whole idea. It does not. CUDA / Volta sm_70: WORKS.

- ggml/src/ggml-cuda/convert.cu:239 dequantize_block_mxfp4 has no __CUDA_ARCH__ guard; helper dequantize_mxfp4 at dequantize.cuh:439, and that file contains zero __CUDA_ARCH__ occurrences. Unguarded end to end. (NUANCE caught by the check: the contrast originally drawn with "the Q8_0 kernel requires Pascal" was overstated — only the specialized dequantize_block_q8_0_f16 fast path is guarded, and that guard exists because FP16_AVAILABLE is defined at the same CC_PASCAL threshold (common.cuh:267), not because of Q8_0. The general Q8_0 dequant path is unguarded too.)
- __dp4a works on V100: common.cuh:51 #define GGML_CUDA_CC_DP4A 610, used at common.cuh:749 #if __CUDA_ARCH__ >= GGML_CUDA_CC_DP4A ... return __dp4a(a,b,c);. sm_70 = 700 ≥ 610, so V100 compiles to the hardware intrinsic, not a scalar fallback.
- CORRECTION — there are THREE MMQ paths for MXFP4, not two (mmq.cuh, ggml_cuda_mmq_get_util_funcs() from line 544): (A) DP4A path, MXFP4 case line 671; (B) Blackwell FP4 MMA, lines 690-707 under #ifdef BLACKWELL_MMA_AVAILABLE (common.cuh:296: CC ≥ 1200 and < Rubin); (C) generic MMA, line 835, outside any Blackwell guard, which is what Turing through Hopper use. CONSEQUENCE FOR JACK: V100 gets path (A), DP4A — the oldest and slowest of the three. Volta predates Turing's int8 tensor-core MMA, so it cannot use (C). This is NOT a regression: DP4A is already the path his Q4_K/Q5_K models take on this box (see local-model-landscape: "V100 still has __dp4a ... which is exactly what llama.cpp's Q4_K etc. integer kernels use"). So MXFP4 is no worse off on Volta than the quants he runs today. CPU / AVX2-without-AVX-512: WORKS, and gets a real vectorized path.
- ggml/src/ggml-cpu/arch/x86/quants.c:918 ggml_vec_dot_mxfp4_q8_0; line 935 #if defined __AVX2__ (uses _mm256_madd_epi16 / _mm256_fmadd_ps), line 965 #elif defined __AVX__, then a scalar tail. No __AVX512* guard anywhere in the function — AVX-512 builds take the same AVX2 branch. Jack's Haswell E5-2699 v3 has AVX2, so it gets the 256-bit vectorized path, not a scalar fallback. STILL UNMEASURED: source inspection proves it compiles and takes the fast-for-Volta path; it does not prove throughput. THE CHEAP DEFINITIVE TEST: gpt-oss-20b is also MXFP4 and only ~12 GB. Download and run it on the V100s — same code path, 12 GB instead of 534 GiB. Do this before committing to anything expensive.

## LIVE FACTS (HF API + config.json, Sep 22 2026) [VERIFIED]

- 1.02T total / 42B active (model card), MIT license, 1M context, Intelligence Index 46 (ties Grok 4.7 for top score open OR closed; GLM-5.3 full is 45)
- *** SIZE — CORRECTED. THE EARLIER "524 GB" FIGURE WAS A UNIT ERROR. *** safetensors.total in the HF API is a PARAMETER/ELEMENT COUNT, NOT BYTES. The value 524,121,348,864 is a count of storage elements, and it was wrongly recorded as "524.1 GB". Real figures:
- Actual repo on disk: usedStorage = 573,487,452,632 bytes = 573.5 GB = 534 GiB (this is what a download costs)
- Weight bytes from the dtype breakdown: ~534.8 GB = ~498 GiB. (U8 500,095,254,528 × 1B = 500.1 GB — the mxfp4-packed experts, two 4-bit values per byte; BF16 10,647,286,656 × 2B = 21.3 GB; F8_E4M3 13,378,781,184 × 1B = 13.4 GB; F32 26,496 ≈ 0.)
- config.json confirms the packing: "store_dtype": "mxfp4", "mxfp4_block_size": 32, quantization_config.quant_method: fp8.
- 128 expert shards plus an audio-tokenizer model, an MTP model, a dFlash draft model, and an index.
- architectures: ["MiMoV2ForCausalLM"], model_type: mimo_v2. Multimodal: vision_config (depth 28) and audio_config present.
- config: num_hidden_layers 70, num_attention_heads 128, num_key_value_heads 8, head_dim 192, v_head_dim 128, hidden_size 6144, vocab_size 152576, n_routed_experts 384, num_experts_per_tok 8, n_shared_experts null, max_position_embeddings 1048576, partial_rotary_factor 0.334. NO MLA fields — plain GQA (128 Q / 8 KV) with asymmetric K/V head dims.
- NOT PREVIOUSLY NOTED, and it matters: the config has hybrid full/sliding-window attention — hybrid_layer_pattern, sliding_window: 128, separate swa_* fields. This likely makes the real KV cost LOWER than the plain-GQA figure below, but it is also exactly the architecture class flagged in cpu-moe-speed-levers as HIGH RISK for prompt-cache breakage ("advanced cache operations ... are not possible when using SWA cache"). Investigate before trusting either the KV number or multi-turn caching.

## *** IT SHIPS ALREADY ~4-BIT. THERE IS NO Q4 STEP TO WIN SPACE. ***

534.8 GB of weight bytes ÷ 1.02T params = ~4.19 bits per weight natively (mxfp4 experts). Unlike GLM-5.3, where BF16 → Q4 is a real 4x compression, MiMo's weights are already there. Going below 4 bits means quantizing already-quantized weights: compounding loss, no published quality table. FIT: ~498 GiB of weights against 503 GiB RAM leaves ~5 GiB — worse than the ~15 GiB in the first draft, because of the unit error above. It does NOT fit properly; it survives only via mmap paging (residency rule in model-storage-plan), and at 498 GiB it cannot fit one socket (~251 GiB) either, so it eats the same cross-socket QPI penalty as GLM-5.3.

## SPEED AND CONTEXT ARITHMETIC (estimated, NOTHING measured on Jack's box)

- Decode: 42B active × 4.19 bits = ~22.0 GB/token → ~1.8 t/s at his measured ~39 GB/s. With attention (~18B active, dense, always on) moved to the V100s: ~11.8 GB/token → ~3.3 t/s, ~4.0 with NUMA tuning. Still slightly FASTER per token than GLM-5.3 (24.8 GB/token) because 4.19 bpw is leaner than GLM's 4.96. (The unit correction barely moved this: 4.11 → 4.19 bpw.)
- KV cache, plain-GQA upper bound: 8 kv heads × (192 K + 128 V) × 2 bytes × 70 layers = 350 KiB/token at f16 → ~36 GiB budget ≈ 105K tokens; ~51 GiB ≈ 150K. Treat as an UPPER BOUND — the hybrid SWA layers above should make the real figure lower.
- BUT SEE the prefill reality check in glm-5.3-download — allocatable context is NOT usable context on a CPU MoE.

## REMAINING BLOCKERS, in order

- mxfp4 support CLEARED, see above. Throughput still unmeasured; run the gpt-oss-20b test.
- NO Pro GGUF EXISTS [VERIFIED via HF API filter=gguf, not just a name search]. Every MiMo-V2.6 GGUF is Flash or Distill-Qwen-9B: ggml-org/MiMo-V2.6-Flash-RL-GGUF, AesSedai/MiMo-V2.6-Flash-GGUF, ProCreations/MiMo-V2.6-Flash-RL-IQ3_XXS-GGUF, TrevorJS/MiMo-V2.6-Flash-RL-GGUF, Baekpica/(two), kernelpool/MiMo-V2.6-Flash-MXFP4-GGUF. A Pro derivative exists in MLX (mlx-community/MiMo-V2.6-Pro-RL-mxfp4-q8) but not GGUF. Caveat: absence is only as strong as HF indexing. Self-conversion needs ~1,032 GiB of disk concurrently (534 GiB source + ~498 GiB output) — the 990 PRO cannot supply it; math in model-storage-plan. WATCH FOR A COMMUNITY Pro GGUF — conversion merged Sep 22, a Flash MXFP4 GGUF already exists from kernelpool, so a Pro one will likely follow within weeks and removes this blocker entirely.
- ik_llama.cpp support looks shaky. Issue #1769: MiMo V2.5 Pro GGUFs fail to load with tensor 'blk.0.attn_q.weight' not found due to fused QKV, unresolved. PR #29257 is mainline only. So the ~1.5-1.9x engine lever may not apply to MiMo.
- Multimodal towers (vision depth 28, audio, audio-tokenizer) will likely be dropped by conversion; excluding them is a free saving with zero text-quality cost.
- RAM is the real unlock, not disk. ~128 GiB more makes this comfortable. Z10PG-D16 has 16 DIMM slots (currently 16×32 GiB). CAVEAT: populating all 16 slots with quad-rank 64GB LRDIMMs commonly downclocks DDR4-2133 to 1866 or 1600 — and since decode speed IS bandwidth ÷ bytes-per-token, a downclock to 1600 costs ~25% speed. You could end up with a model that fits and runs slower than it would have. Check the Z10PG-D16 QVL first.

## USE-CASE REALITY CHECK At ~3 t/s, 50,000 tokens of output is 4.6 hours of generation — and an agentic build is dozens of turns each re-reading the conversation, with Jack's own Jarvis logs showing 82 tool calls in a single turn (jarvis-run-host-commands). If prompt caching doesn't hold across turns (and the hybrid SWA attention above makes that a live risk), that is days, not hours. MiMo at 3 t/s is an "ask one genuinely hard question, come back after dinner" model, not an agentic builder. Sensible split: Qwen3.8-27B at 83 t/s does the building; MiMo is reserved for problems where 46-index reasoning changes the answer.

## LESSON WORTH KEEPING: HF API safetensors.total IS NOT BYTES

It is a sum of tensor element counts. Use usedStorage for real repo bytes, or sum the parameters dtype breakdown × bytes-per-dtype for weight bytes. Reading it as bytes understated this model by ~50 GB and made the RAM fit look 10 GiB roomier than it is. Applies to any future HF size estimate.

Sources: huggingface.co/XiaomiMiMo/MiMo-V2.6-Pro-RL (card, HF API ?blobs=true, config.json); github.com/ggml-org/llama.cpp/pull/29257 and its .diff; llama.cpp master source ggml-cuda/{convert.cu,mmq.cuh,common.cuh,dequantize.cuh} and ggml-cpu/arch/x86/quants.c; github.com/ikawrakow/ik_llama.cpp/issues/1769; HF API model search with filter=gguf.

## *** Sep 23 2026 — A Pro GGUF NOW EXISTS, AND MiMo IS RUNNABLE ON THIS BOX. BLOCKER 2 IS CLEARED. [VERIFIED live via HF API] ***

Jack: "there HAS to be a way for me to run it." There is. The self-conversion plan and the ~1,032 GiB disk problem in Blocker 2 are both obsolete.

### THE FILE

kernelpool/MiMo-V2.6-Pro-RL-MXFP4-GGUF — usedStorage 560,088,098,208 B. Contents: | file | bytes | | MiMo-V2.6-Pro-RL-MXFP4.gguf.part1 | 480,000,000,000 | | MiMo-V2.6-Pro-RL-MXFP4.gguf.part2 | 77,146,510,560 | | model total | 557,146,510,560 B = 557.1 GB = 518.88 GiB | | MiMo-V2.6-Pro-RL-DFlash-Q8_0.gguf | 2,941,587,648 (2.94 GB) | These are RAW SPLITS, not gguf-split shards. Join per their README: cat ...part2 >> ...part1 then mv ...part1 ...gguf. Appending to part1 rather than writing a third file keeps the transient cost to part2's size: 634 GB peak against 815 GB free on the 990 PRO. Fits. VISION AND AUDIO ARE ALREADY DROPPED ("no vision encoder is included"). So the "conversion will drop the towers, free saving" note above is already banked — there is no further saving there, and 518.88 GiB is the text-only figure. *** CORRECTS THIS FILE'S "~498 GiB of weights": that was derived from the SOURCE dtype breakdown. The real GGUF is 518.88 GiB, ~21 GiB larger (the F8_E4M3 tensors upconvert, plus GGUF metadata). Against 503 GiB RAM the raw model is SHORT BY ~15.9 GiB — it does NOT fit unaided. ***

### *** THE FIX, AND IT WAS ALREADY IN THIS FILE AS A SPEED LEVER: -ot MAKES IT FIT. ***

Split the 518.88 GiB: mxfp4 experts ≈ 500.1 GB = 465.8 GiB; everything else (attention, dense, embeddings, norms) ≈ 53 GiB.

-ngl 99 -ot "ffn_.*_exps.*=CPU"

- Experts alone in RAM: 465.8 GiB against 503 GiB — fits with ~37 GiB spare.
- CONSTRAINT: the non-expert slice is ~53 GiB and only ~31.5 GiB of VRAM exists (2 x 16,144 MiB usable), so a FULL offload is impossible. Offload what fits, ~30 GiB → RAM ~489 GiB, under 503. It fits without paging. Remaining headroom ~14 GiB for KV + OS, i.e. tight but resident.
- Same flag roughly halves bytes/token, so it is also the speed lever: ~1.7 t/s → ~3.3 t/s (at the newly measured ~36.6 GB/s, see system-performance-levers — slightly below the ~39 used elsewhere). REQUIRES THE 27B STOPPED to free both cards.

### *** THE dFlash DRAFT IS AVAILABLE TO JACK EVEN THOUGH kernelpool DISABLED IT ***

Their README: "DS4 does not run the DFlash sidecar or vision under tensor parallelism yet, so the sidecar is not used for now." That is a limitation of THEIR deployment (two 512 GB Macs, tensor parallel, ~270 GiB resident per rank), not of the file. Jack runs single-node, so the 2.94 GB DFlash-Q8_0 sidecar is usable. Per the speculative-decoding research in cpu-moe-speed-levers, expect ~1.3-1.6x on a CPU MoE (not the GPU-published 1.95x), i.e. plausibly ~4-5 t/s stacked with -ot. --spec-draft-n-max is clamped to dFlash's trained block size.

### FALLBACK IF -ot IS TOO TIGHT: IT STILL RUNS

llama.cpp mmaps by default, so a model larger than RAM pages from NVMe rather than failing. Raw, that is ~16 GiB of paging, about 3% of the model. *** USE mmap, NEVER --mlock HERE *** — per model-storage-plan's residency rule, mlock on a non-resident model converts a graceful slowdown into an OOM kill.

### WHAT WAS CHECKED AND RULED OUT — do not re-derive

- No Pro GGUF below MXFP4 exists anywhere. HF search returns only ProCreations/MiMo-V2.6-Flash-RL-IQ3_XXS-GGUF (Flash, not Pro).
- You cannot easily make one. The source ships mxfp4-packed experts (store_dtype: mxfp4) and llama.cpp's converter hoists the K3 mxfp4 repack, so conversion lands at the same ~4.19 bpw. Requantizing already-4-bit weights is not a supported llama-quantize path.
- jarrelscy/MiMo-V2.6-Pro-RL-ARVQ-hybrid — per-expert ARVQ FP4 books with FP16 block scales, some NVFP4 experts. safetensors + vLLM + custom code, NOT GGUF. No quality benchmarks published. Not usable on llama.cpp.
- Other Pro repos found, none GGUF: dealignai/MiMo-V2.6-Pro-RL-UNCENSORED, servantofares/MiMo-V2.6-Pro-RL.

### RAM UPGRADE RECONSIDERED — THE BLOCKER-5 CAVEAT IN THIS FILE IS WRONG

Blocker 5 warns that 16 x 64 GB quad-rank LRDIMMs "commonly downclock 2133 to 1866 or 1600". The Sep 23 audit found this backwards: Supermicro's E5-2600 v3 memory table gives quad-rank LRDIMM at 5-8 DIMMs/CPU → 1600/1866/2133, while dual-rank RDIMM at 5-8 DIMMs/CPU → 1600/1866 only (which is exactly why Jack's current 16 x 32 GB run at 1866). So the 1 TB LRDIMM path plausibly delivers capacity AND 2133, making MiMo comfortable rather than marginal. Price 64 GB 4Rx4 LRDIMM (PC4-17000L); 64 GB 2Rx4 RDIMM is a DDR4-3200 part that does not apply to this platform.

### USE-CASE VERDICT UNCHANGED

Even fitted and offloaded, ~3-5 t/s. 50,000 tokens of output is hours, and agentic turns re-read the whole conversation. MiMo is the "ask one genuinely hard question and walk away" model; the 27B at ~69 t/s stays the daily driver. Prefill remains unmeasured for this model and is the thing most likely to make long prompts unusable.

## *** Sep 23 2026 — HOW TO MAXIMISE MiMo'S CAPABILITY, AND WHAT EXACTLY TO DOWNLOAD [card + repo read live] ***

### WHAT TO DOWNLOAD: THERE IS EXACTLY ONE OPTION. RE-CONFIRMED.

Searched HF with filter=gguf: kernelpool/MiMo-V2.6-Pro-RL-MXFP4-GGUF is the ONLY Pro GGUF in existence. Everything else returned is Flash or the 9B Distill. No choice of quant, no choice of packager. Three files, all of them: ...MXFP4.gguf.part1 (480,000,000,000 B) + ...MXFP4.gguf.part2 (77,146,510,560 B) + ...DFlash-Q8_0.gguf (2,941,587,648 B).

### *** SAMPLING: temperature 1.0, top_p 0.95 — NOT temp 0. THIS CONFLICTS WITH JACK'S CURRENT SETUP. ***

Xiaomi's card states the recommended settings verbatim: temperature=1.0, top_p=0.95. *** Jack's Open WebUI has temperature: 0 written into the jarvis model row (the Sep 22 speed fix, worth +24% on the 27B because it maximises MTP draft acceptance). That value is MODEL-SPECIFIC and must NOT be inherited by MiMo. *** Running a model far off its recommended sampling is a real quality risk, and the speed argument for temp 0 is much weaker here anyway — MiMo's dFlash is a block-diffusion draft, not a distribution-matching MTP head. Give MiMo its own Open WebUI model row with temp 1.0 / top_p 0.95.

### *** THE DRAFT: 5-LAYER SPECULATIVE DECODER, 7 TOKENS PER FORWARD PASS. SO --spec-draft-n-max 7. ***

The card describes it as a 5-layer speculative decoder predicting 7 subsequent tokens per forward pass, DFlash-style. Per llama.cpp's docs, --spec-draft-n-max is clamped to the draft's trained block size, so 7 is the number — not the 5 that is optimal for the 27B's MTP head, and not the 15 in llama.cpp's generic DFlash example. Do not sweep blindly; start at 7.

### CAPABILITY THE CARD CLAIMS (vendor, no neutral index beyond AA's 46)

| domain | benchmark | score | | Code agent | DeepSWE v1.1 | 71.9 | | General agent | Toolathlon-Verified | 76.9 | | Agent tasks | Terminal Bench 2.1 | 89.9 | | Cybersecurity | CyberGym | 94.0 | | Visual agent | MiMo VisualCoding | 72.3 | Context 1M, explicitly positioned for "long repositories, tool traces, and multi-session agent runs."

### *** THE CAPABILITY YOU LOSE AND CANNOT GET BACK FROM THIS FILE: VISION. ***

kernelpool's GGUF has no mmproj and no vision encoder (their README: "no vision encoder is included"). MiMo VisualCoding 72.3 is one of its five headline benchmarks, and it is simply absent from the only Pro GGUF that exists. The ONLY route to MiMo-with-vision is a self-conversion from the 573.5 GB source — llama.cpp PR #29257 does support converting Pro with vision. Not recommended: it costs the full source download plus a multi-hour conversion, and the vision tower would then need VRAM that the -ot offload plan is already spending on non-expert tensors. Flagged so the tradeoff is a decision, not a surprise. If vision matters more than the 46 index, the 27B already has a working mmproj.

### THE FULL RUN RECIPE, assembled from everything measured

-m MiMo-V2.6-Pro-RL-MXFP4.gguf

-md MiMo-V2.6-Pro-RL-DFlash-Q8_0.gguf --spec-draft-n-max 7

-ngl 99 -ot "ffn_.*_exps.*=CPU"        # THE fit lever AND ~2x decode

```bash
--numa distribute                       # + numactl --interleave=all
--threads 36 --threads-batch 72         # physical for decode, logical for prefill
-b 4096 -ub 4096                        # prefill only, ~2x, free
                                        # mmap ON. NEVER --mlock (non-resident model -> OOM kill)
```

Temp 1.0 / top_p 0.95 set in the client, not the server. Stop the 27B first to free both V100s. KV NOTE: the 350 KiB/token figure elsewhere in this file is a plain-GQA UPPER BOUND. The config has hybrid_layer_pattern with sliding_window: 128, so most layers cache only 128 tokens and the real figure should be far lower. Measure it from the startup log before planning a context size — and treat the hybrid-SWA prompt-cache breakage risk as live until tested.

### HONEST CEILING

~2-3 t/s realistic, ~3.1 optimistic, ~4-5 if dFlash delivers 1.3-1.6x. Prefill is unmeasured for this model on any hardware and is the thing most likely to make it unusable — comparable hardware manages only 16-44 t/s prefill on a big MoE (cpu-moe-hardware-anchors), which at 16 t/s makes a 32K prompt a 33-minute wait before the first token. MiMo is the ask-one-hard-question model. The 27B at ~69 t/s remains the daily driver.

## *** Sep 23 2026 — THE mmap FALLBACK IS BETTER-SOURCED THAN THIS FILE IMPLIED, AND THERE IS AN EXPERT-STREAMING FUTURE ***

Jack asked "how do I load MiMo V2.6 Pro?" This pass verified the over-RAM mechanism rather than asserting it.

- llama.cpp discussion #19163 "Does llama.cpp offload MoE to disk?" — confirms the mechanism verbatim: "Weights are read from disk on-demand" with mmap on; mmap "treats the full file size as additional addressable RAM" and the OS pages in what is touched. llama.cpp does not itself offload to disk — it relies on the OS. --no-mmap on an over-RAM model is an OOM crash; --mlock is the same mistake. Degradation is driven by access-pattern locality: "if your access pattern jumps all over the mmap'd file" the OS thrashes.
- discussion #18758 "Mmap faster than direct I/O for MoE models" — mmap beats O_DIRECT specifically in the "100% or 150% of RAM" regime, because the page cache keeps the hot set resident across loads; O_DIRECT bypasses it and is reported "at least 10x longer" on repeated loads. Prefetching was DISABLED in those tests because it caused thrashing when the model exceeds RAM — relevant if Jack ever tunes readahead. No t/s figures published. So MiMo at 103% of RAM is squarely in the regime where mmap is the documented right answer, and the ~3% overflow is the best possible case for it. Still unmeasured on his box.
- FUTURE, NOT AVAILABLE YET: discussion #27149 "Expert-Aware SSD Streaming for MoE Models." Prototype (TinyGiant) fetches only the active experts per token instead of whole layers: on Qwen3-30B-A3B, I/O cut 11.4x (263 MB → 31 MB per layer) and 0.9 → 4.7 t/s, ~6.3 projected with double-buffering, on an M1 MacBook Pro with 16 GB RAM holding a ~1-2 GiB footprint. A PROPOSAL, NOT MERGED. If it ever lands it would matter enormously here, since MiMo activates 8 of 384 experts. Watch it.

### ONE CORRECTION TO AN EASY MISREAD OF THE REPO LISTING

MiMo-V2.6-Pro-RL-DFlash-Q8_0.gguf at 2,941,587,648 B is the dFlash speculative DRAFT head, not a smaller quantization of the model. A summarizer reading the file list will call it "a Q8_0 quant option" — it is not, and there is still exactly one Pro quant (MXFP4). Recorded so the mistake is not repeated.
