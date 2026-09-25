# qwen38-flash-next

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 22, 2026).
> Cowork-only links kept as page names.
>
> Summary: Qwen3.8-Flash-Next (qwen4exp) — the model found Sep 22 2026 that likely beats GLM-5.3 as Jack's practical big-model slot on jarvis-1. Architecture, verified GGUF sizes, measured third-party speeds, and why it is 6-10x faster than GLM-5.3 on his box. Read before any big-model or orchestrator slot decision.

Found Sep 22 2026 while researching orchestrator slots. NOT present in local-model-landscape's Sep 22 survey, which checked the Artificial Analysis open-weights top-13 and missed this because it sits below MiMo/GLM-5.3 on raw index score. Companions: cpu-moe-speed-levers (the speed arithmetic frame), orchestrator-slot-plan (where it fits). Claims below survived a blind-agent verification pass Sep 22 2026 EXCEPT where marked; one size figure was corrected by that pass and the corrected value is what is written here.

## WHY THIS MATTERS: it is the first big model that is both capable AND interactive on Jack's box

Every big model researched so far (GLM-5.3, GLM-5.3-Flash, Hy4-preview, MiMo-V2.6-Pro) lands at 1.3-5 t/s because they have 40-49B active params. Flash-Next has 6B active. That is the whole story — decode is bandwidth ÷ bytes-per-token, and this reads ~1/7th the bytes GLM-5.3 does.

## ARCHITECTURE [VERIFIED against the Qwen model card]

- 125B total with 6B activated per token, plus a 51B n-gram embedding table and a 4B MTP module. Qwen's own headline is "125B total"; the ~180B aggregate is the sum of the three components and is NOT a figure Qwen quotes — do not cite 180B as the model size.
- 48 layers as 12 x (3 x GatedDeltaNet->MoE + 1 x QSA->MoE) — the 3:1 ratio. 512 experts, 10 routed + 1 shared active.
- Qwen Sparse Attention (QSA), 2048-token budget at 4:1 compression.
- 262,144 native context, extensible to 1,000,000 via YaRN.
- Multimodal: integrated Qwen3-VL ViT; mmproj/vision projector ships with the GGUFs.
- n-gram table indexes ~20 million bigrams and trigrams. It is a sparse LOOKUP, not read in full per token — this is why 6B active is the real cost.

## LLAMA.CPP SUPPORT: MERGED. RUNS ON STOCK BUILD. [VERIFIED]

PR #27742 "model: add Qwen3.8-Flash-Next (qwen4exp)" (danielhanchen) MERGED Aug 27 2026 by ngxson. Validated on CPU, CUDA and HIP/ROCm backends. Jack's build b11089 (Sep 21) postdates the merge, so it should already be in the binary — CHEAP CHECK OWED: grep -ril "qwen4exp" ~/llama.cpp/src/. This is the key difference from every other big model on file: no fork, no patch stack, no open PR. Compare GLM-5.3-Flash (3 stalled/abandoned mainline PRs), MiniMax-M3 (3 competing PRs), K2 Horizon (fork only).

## VERIFIED GGUF SIZES — unsloth/Qwen3.8-Flash-Next-GGUF (1,525,862 downloads, modified Sep 2 2026)

- UD-Q4_K_XL = 111,334,654,784 bytes = 111.3 GB = 103.7 GiB. (CORRECTED by the verification pass; an earlier draft said 121.3 GB — that was an arithmetic error, do not reintroduce it.)
- UD-Q2_K_XL = 78,869,128,864 bytes = 78.9 GB = 73.4 GiB.
- Separate MTP draft GGUFs published in the same repo: mtp-...-Q8_0.gguf 4,137,429,120 B; mtp-...-Q4_K_M.gguf 2,786,204,800 B; plus "shared" variants. So speculative decoding is available out of the box, no vocab-matching hunt required — this is the thing GLM-5.3 does NOT have a confirmed GGUF path for.
- Other ladders present: UD-IQ1_S/M, UD-IQ3_XXS, UD-IQ4_XS, UD-Q3_K_XL, UD-Q5_K_XL, UD-Q6_K_XL, Q8_0, BF16.
- Alternative quantizer: ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF. Q2_0 2.40 bpw 66.4 GB (fastest: 367.49 t/s prefill), IQ2_XS 2.50 bpw 68.0 GB, IQ3_XXS 3.00 bpw 75.8 GB (their recommended pick, claimed 99.4% of base task average at 4.7x smaller). All include a 0.91 GB shared vision projector. [VENDOR] claims.
- AtomicChat/Qwen3.8-Flash-Next-GGUF ships "M64" builds that put the 51B n-gram table in ITS OWN SHARD — relevant if RAM is ever tight, see the M1 Max result below.

## FIT ON JACK'S BOX — this is what makes it the standout

Against 503 GiB total RAM, ~251 GiB per socket:

- UD-Q4_K_XL at 103.7 GiB FITS INSIDE ONE SOCKET. Two consequences the other models cannot claim:
- No cross-socket QPI tax. GLM-5.3 at Q4_K_XL (435 GiB) is FORCED to span both sockets, so ~half its weight reads cross QPI at ~19.2 GB/s. Flash-Next never does.
- NUMA mirroring is viable at FULL Q4 quality — 2 x 103.7 = 207.4 GiB against 503 GiB, with ~295 GiB to spare. cpu-moe-speed-levers establishes mirroring is worth a measured 1.47-1.63x, and that NO quant of GLM-5.3 full is both mirrorable and good. Flash-Next is mirrorable at its BEST quant.
- Disk: 111.3 GB fits the 990 PRO with hundreds of GB spare. No HDD needed for this model.

## SPEED — ESTIMATED for Jack, but anchored on real third-party measurements

BANDWIDTH ARITHMETIC: 111.33e9 bytes x 8 / 180e9 params ~= 4.95 bpw. 6B active x 4.95/8 = ~3.7 GB/token, plus sparse n-gram row reads.

- At Jack's measured ~39 GB/s: ~10.5 t/s. At the downclock-corrected ~34 GB/s: ~9.2 t/s.
- NUMA-mirrored (~1.5x): ~14-17 t/s. Plus MTP speculative decoding (expect ~1.3-1.6x on CPU per the CPU-discount note in cpu-moe-speed-levers): ~18-27 t/s.
- Compare GLM-5.3 full Q4_K_XL: 24.8 GB/token, 1.6 t/s baseline, 2.5-4 t/s fully optimized. Flash-Next is roughly 6-10x faster. ALL OF THE ABOVE IS ESTIMATE. Nothing measured on Jack's box. Same rule as everywhere in this memory: measure it.

## REAL MEASURED NUMBERS FROM OTHERS [VERIFIED]

- M1 Max 64GB (lilting.ch): pp512 181.69 t/s, tg128 17.59 t/s, sustained ~18 t/s in real tasks (16.3 under long reasoning). Quant AtomicChat AD-3.84bpw-IQ4_XS-M64, 84.9 GB / 28 shards. The 51B n-gram table (38.4 GB, its own shard) stayed on SSD via mmap and was never wired into memory — only the rows actually looked up entered the file cache. Active model in memory 45.8 GB. This proves the n-gram table does NOT have to be resident, which is a free RAM lever if Jack ever wants it.
- From unsloth's speed thread (all GPU, for reference not transfer): 4x RTX 5090 32.5-84 t/s; 2x 4090D-48GB 44.66 t/s decode / 1796.81 prefill; RTX 6000 PRO 96GB 59.70 t/s; 5070Ti+5060Ti (2x16GB) 23.32 t/s on UD-IQ3_XXS; single RTX 3090 24GB + 128GB RAM 15 t/s at 30K prompt on UD-Q4_K_XL; M1 Ultra 128GB 20 t/s on UD-IQ1_S; Ryzen 9800X3D + RTX 5080 16GB 27.5-29 t/s with speculation on UD-IQ3_XXS.
- The RTX 3090 24GB + 128GB RAM data point (15 t/s) is the closest shape to Jack's setup (small VRAM, model mostly in system RAM) and lands right on the estimate above.

## CAPABILITY [VERIFIED]

- Artificial Analysis Intelligence Index v4.3.2 = 40. Same-version peers confirmed this pass: MiMo-V2.6-Pro 46, GLM-5.3 (max) 45, GLM-5.3-Flash 42, Qwen3.8-27B (xhigh) 34. Hy4-preview has NO Artificial Analysis page at all — that earlier comparison was never on the same index.
- So: +6 over the 27B Jack runs today, -5 from GLM-5.3 full, at 6-10x GLM's speed.
- AA notes it is "slower than average" and "very verbose" (240M output tokens on the index run). Verbosity is a real cost at these speeds — expect to need reasoning-effort control.
- SWE-bench Pro 62.5 (vs DeepSeek-V4-Flash-0731's 56.0); JobBench 55.7 (vs 41.3). Leads or ties its comparison set on most agentic and coding benchmarks. [VENDOR]
- Pricing on hosted APIs $0.15/M in, $0.47/M out; output speed 54.1 t/s, TTFT 2.71s.

## KNOWN RISKS / OPEN ITEMS

- Gated DeltaNet CUDA prefill is slow. llama.cpp issue #22967 (OPEN RFC): large prompt processing still goes through the token-sequential kernel; the chunked CUDA prefill implementation is PR #26001, open and under review, NOT merged. The chunked algorithm DOES already exist in the CPU reference path, so CPU prefill is less affected than CUDA. Practical read: do not expect the GPUs to rescue prefill on this model.
- Prompt-cache risk is UNTESTED. Gated DeltaNet is a recurrent-state architecture, exactly the class flagged HIGH RISK in cpu-moe-speed-levers for KV-cache reuse breaking and forcing full prompt reprocessing every turn. Detect with -lv 4 and the "forcing full prompt re-processing due to lack of cache data" line. This is the single biggest thing that could eat the speed win on multi-turn agentic use — TEST IT FIRST.
- n-gram table wants ~51 GB of host RAM if kept resident. Jack has room; the M1 Max trick is the fallback if he ever doesn't.
- Volta/sm_70 specifically is unverified for this architecture, as always.

Sources: github.com/ggml-org/llama.cpp PR #27742, issue #22967, PR #26001; huggingface.co/Qwen/Qwen3.8-Flash-Next (card), HF API tree for unsloth/Qwen3.8-Flash-Next-GGUF and ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF; artificialanalysis.ai/models/qwen3-8-flash-next; lilting.ch M1 Max test; unsloth/Qwen3.8-Flash-Next-GGUF discussion #3; akash.network Flash-Next architecture writeup; kaitchup.substack.com review.
