# V100 hardware constraints, model shortlist, benchmark distrust

> Copied verbatim from Cowork (melange-wiki) on Sep 24 2026. Cowork-only links kept as page names.
> Summary: What Jack can actually run on his 2x Tesla V100 (32GB VRAM, Volta sm_70) — the CUDA/driver
> constraints, the model shortlist as of Sept 2026, and which published benchmark numbers are fake.
> Read before recommending models, drivers or build flags for the ESC4000 build.

Researched Sep 9 2026 and put through an adversarial verification pass. Related: esc4000-parts-order, local-ai-setup

HARDWARE CONTEXT: 2x Tesla V100 PCIe 16GB = 32GB VRAM total, Volta, compute capability 7.0. 256GB DDR4-2133. Dual Xeon E5-2699 v3. Ubuntu 24.04.
(Superseded Sep 21: RAM is now 503 GiB, running at 1866 MT/s — see below.)

## THE HARD CONSTRAINT: CUDA MUST BE 12.9 OR OLDER

* CUDA 12.9 (latest patch 12.9.2, May 2026) is the LAST toolkit that can target sm_70. CUDA 13.0 removed it outright; nvcc 13.x REJECTS sm_70, so `-DCMAKE_CUDA_ARCHITECTURES=70` fails to compile at all
* CUDA 12.9 release notes, verbatim: "Maxwell, Pascal, and Volta architectures are now feature-complete with no further enhancements planned. While CUDA Toolkit 12.x series will continue to support building applications for these architectures, offline compilation and library support will be removed in the next major CUDA Toolkit version release."
* THE TRAP: Ubuntu 24.04's NVIDIA CUDA repo now serves 13.x by default. Installing "the latest CUDA" silently produces a machine where nothing builds for his cards. The toolkit version must be pinned to 12.9.x
* Driver: R580 is the LAST branch supporting Maxwell/Pascal/Volta (confirmed by NVIDIA via Phoronix). NVIDIA's datacenter matrix lists R580 as a Long Term Support Branch with EOL June 2028; endoflife.date says active support ended 4 Aug 2026 and security-only to 4 Aug 2028. Dates differ by source; the actionable fact is R580 is past active support, security fixes only, until roughly mid-2028
* PyTorch: 2.11 drops sm_70 from its CUDA 12.8 wheels. Volta users take the CUDA 12.6.3 wheel instead

## LLAMA.CPP BUILD FACTS (verified against the repo, not blogs)

* There are NO Linux CUDA prebuilt binaries in llama.cpp releases at all. Linux assets are CPU, Vulkan, ROCm, OpenVINO and SYCL only; every CUDA prebuilt is Windows. So building from source is required regardless of architecture
* ggml/src/ggml-cuda/CMakeLists.txt appends `50-virtual 61-virtual 70-virtual` by default when CUDAToolkit_VERSION < 13, so sm_70 IS covered by default on a 12.x toolkit. The CUDA 13.3 build excludes it via a `VERSION_LESS "13"` guard
* Correct build flag remains `-DCMAKE_CUDA_ARCHITECTURES=70`, but ONLY works on a CUDA <=12.9 toolkit

## VOLTA CAPABILITY REALITY

* 1st-gen tensor cores: FP16 in, FP32 accumulate, ONLY. No BF16 (Ampere sm_80+), no INT8/INT4 tensor cores (Turing sm_75+)
* IMPORTANT NUANCE: "no int8" is true only of TENSOR CORES. V100 still has __dp4a (INT8 dot product on regular CUDA cores, Pascal sm_61+), which is exactly what llama.cpp's Q4_K etc. integer kernels use. So int8-quantized inference works fine, it just never touches tensor cores
* BF16 GGUFs get converted and run as FP16; there is no native BF16 path
* Memory bandwidth 900 GB/s per card (HBM2), which is the V100's real advantage over 24GB consumer cards

## MULTI-GPU IN LLAMA.CPP (verified in common/arg.cpp and src/llama-arch.cpp)

* Split modes are {none, layer, row, tensor}. `layer` is the default and is PIPELINE parallel, so you get roughly ONE card's bandwidth, not the sum of two. `row` is deprecated and slow. `tensor` splits weights and KV across GPUs, documented as "parallelized, EXPERIMENTAL"
* Tensor split mode is gated by a per-architecture DENYLIST (llm_arch_supports_sm_tensor), NOT by an MoE rule. Widely repeated claim "tensor mode doesn't support MoE" is FALSE. qwen3moe IS supported. Excluded architectures are mostly hybrid/SSM/linear-attention: MAMBA, MAMBA2, JAMBA, FALCON_H1, NEMOTRON_H, GRANITE_HYBRID, KIMI_LINEAR, PLAMO2, MINIMAX_*, plus some MoE ones: OLMOE, DEEPSEEK2/32, NEMOTRON_H_MOE, BAILINGMOE3, GROK
* Practical consequence: Nemotron 3.5 Lightning cannot use tensor split; Qwen3.6/3.8 MoE can
* (Sep 21: `-sm tensor` is BROKEN on V100 anyway — see below.)

## MODEL SHORTLIST THAT FITS 32GB AT 4-BIT (all verified real, Sept 2026)

* Qwen3.8-27B — 14 Aug 2026, 27B DENSE, 262K ctx (extendable to 1M), Apache 2.0, ~16-17GB at Q4_K_M. BEST FIT of the group
* Qwen3.6-35B-A3B — Apr 2026, 35B total / 3B active MoE (256 experts, 9 active). 22.1GB at UD-Q4_K_M, 17.7GB at UD-IQ4_XS. Fast because only 3B active
* Gemma 4 31B — 2 Apr 2026, 30.7B dense multimodal, ~25.2GB at Q6_K
* Gemma 4 26B-A4B — 2 Apr 2026, 25.2B total / 3.8B active MoE, QAT Q4_0 available (NOTE: Gemma 4 is APRIL 2026; several blogs wrongly say June)
* GLM-4.7-Flash 30B-A3B — ~20 Jan 2026, ~31B / ~3B MoE, MIT license, ~24.8GB at Q6_K
* NVIDIA Nemotron 3.5 Lightning 30B-A3B — 11 Aug 2026, 30B/3B Mamba-2 + MoE + attention hybrid, OpenMDW-1.1, official ggml-org GGUF, tiny KV cache (~6KB/token) so great for long context. CANNOT use tensor split
* Muse Glimmer 30B (Meta Superintelligence Lab) — Aug 2026, 29.6B dense multimodal incl. ~1.8B vision encoder, Apache 2.0
* IBM Granite 4.2 30B — Aug 2026, Apache 2.0 (date from aggregator, +/- a week)
* Poolside Laguna XS 2.1 — early Jul 2026, 33B total / 3B active MoE, 256K ctx, agentic coding
* Devstral Small 2 24B — 9 Dec 2025 (NOT a 2026 model), 24B dense, Apache 2.0, 256K ctx, ~25.1GB at Q8_0. Best local coding-agent option
* TOO BIG for 32GB: Kimi K3 (~2.8T), LongCat-2.0 (1.6T), DeepSeek V4-Pro (1.6T/49B), Kimi K2.6 (~1T/32B), Laguna S 2.1 (118B/8B), Inkling (975B/41B), GLM-5.2, Qwen3-235B-A22B

## BENCHMARK NUMBERS TO DISTRUST

* Blogs circulating "Tesla V100 32GB: Qwen3.6-35B-A3B at 98.8 tok/s decode, 352 prefill" and "Qwen3.6-27B Q4_K_M 32.9 tok/s" are NOT credible for a SINGLE V100: Qwen3.6-27B Q4_K_M is 16.8GB and 35B-A3B UD-Q4_K_M is 22.1GB, so neither fits in one 16GB card before any KV cache. 33 tok/s on 16.8GB of weights implies ~554 GB/s effective, ~62% of peak, at or above llama.cpp's best-case efficiency and impossible across a pipelined 2-card split
* No credible V100 benchmark for these models exists anywhere. Nearest real data point: 2x RTX 5060 Ti 16GB running Qwen3.6-27B Q4_K_M measured 49-175 ms/token, i.e. ~6-20 tok/s. Volta has ~2x the per-card bandwidth but that does not stretch to 33 tok/s
* TREAT ALL PUBLISHED V100 TOK/S FIGURES AS UNVERIFIED. Measure on the actual machine before believing anything

ECOSYSTEM SUNSET NOTE: this hardware is on a clock. CUDA compilation for Volta is already gone from 13.x, PyTorch is dropping it from newer wheels, and driver support is security-only. Everything works today and will keep working, but the window for NEW tooling supporting sm_70 is closing. Worth factoring into any future GPU purchase.

## FIRST REAL MEASUREMENT ON JACK'S HARDWARE — Sept 12 2026

2x Tesla V100 PCIe 16GB, llama.cpp build b10918-82d6bb284, CUDA 12.x, sm_70, default layer split, -ngl 99. Model: ggml-org/Qwen3.8-27B-GGUF:Q4_K_M (reports modalities: text, vision, video)

MEASURED: Prompt 145.8 t/s, Generation 32.0 t/s

This partially REFUTES the skepticism recorded above. The "~33 tok/s for a 27B Q4_K_M" figure circulating on blogs is achievable on TWO V100s, just not on one. Working back: ~16.5 GB of weights at 32 t/s implies ~528 GB/s effective, about 59% of a single card's 900 GB/s peak, which is a normal real-world llama.cpp efficiency rather than an impossible one. The claim that this is "at or above llama.cpp's best case" and "impossible across a pipelined 2-card split" was wrong. What remains correct: the figures are not achievable on a single 16GB V100, because the weights do not fit.

Use 32 t/s generation / 146 t/s prompt as the baseline for this machine. Compare any future model, quant, or split-mode change against it.

## GLM-5.3 FEASIBILITY ON JACK'S BOX — researched Sept 12 2026

Jack asked whether he can run or at least download GLM-5.3 right now. Two different models, two different answers.

GLM-5.3 (full): ~744B total / ~40B active MoE, 1M ctx, shares a base with GLM-5.2. Custom "GLM-5.3 License", not MIT: companies over $10B revenue need Z.ai security review; individuals effectively get MIT terms.

* UD-IQ1_S ~217 GB disk, ~230 GB combined memory floor
* UD-IQ2_M 239 GB disk, 245 GB+ floor
* UD-Q4_K_XL ~420 GB — impossible here
* Reference perf cited: 3-9 tok/s at 2-bit on a 256GB Mac Studio or 256GB DDR5 CPU-offload build. Jack has DDR4-2133 (~68 GB/s per socket, NUMA-split), so expect materially worse, low single digits
* VERDICT: IQ1_S technically fits 256 GB but with almost no headroom, and 1-bit quality is poor. Not recommended.

GLM-5.3-Flash: 320B total / 18B active, hybrid attention = 34 layers KDA linear attention + 11 layers NoPE Sparse MLA with a "lightning indexer" (top-2048 KV retrieval). 1M ctx. Claims 3.01x less attention compute and 4.44x smaller KV cache than full GLM-5.3.

* 1-bit: 93 GB disk, 128 GB+ memory
* UD-Q4_K_XL ~199-200 GB (matches Jack's earlier Sept research), fits 256 GB with ~50 GB headroom
* VERDICT: this is the plausible one, not the full model.

THE GATE: llama.cpp architecture support is unconfirmed. The Flash deep-dive documents deployment via vLLM, SGLang, TokenSpeed and KTransformers and says nothing about llama.cpp. KDA linear attention is exactly the architecture class on llama.cpp's tensor-split denylist, and relates to the still-open sm_70 fused-Gated-DeltaNet question. GGUFs existing on HF (unsloth, AtomicChat) does NOT prove Jack's build can load them. FREE TEST BEFORE ANY DOWNLOAD: grep his own llama.cpp source for the architecture string rather than spending hours of bandwidth.

DRIVE RISK — specific to this machine. A 100-200 GB sustained write is the same workload class that killed the first NVMe (nvme-drive-failure), and the replacement already moved 100% -> 98% available_spare after only 60 GB. Check SMART before and after any large model pull, against the tripwires stored in that file.

## Sept 12 2026 — GLM-5.3-FLASH AND HY4: BOTH STILL NO, now with PR-level evidence

GLM-5.3-Flash (321.3B / 18B active): llama.cpp support is NOT MERGED. TWO competing open PRs exist, which means the design is not settled:

* PR #27754 (danielhanchen / unsloth), "model: add GLM-5-Next (GLM-5.3-Flash)" — OPEN as of Aug 30 2026. Implements KDA recurrent attention with gated mechanisms, hybrid dense/sparse attention with pooled indexer selection, MoE FFN with clamped SwiGLU, mHC wide residual blocks derived from DeepSeek-V4. Verified on NVIDIA B200 with IQ1_S; Metal tested. Requires `NVIDIA_TF32_OVERRIDE=0` and `-fa off` for correctness. Precision-sensitive tensors (indexer, KDA gates) must retain source precision or selection drifts. Known instability past 65K context on Metal.
* PR #27752 (eauchs), "model : add GLM-5.3-Flash (glm5next)" — also open. Consequence for Jack: his build b10918 cannot load it at all. And B200 verification says nothing about sm_70 — the KDA and DSA kernels would still need a Volta path, which is the same open question as fused Gated DeltaNet.

## Sep 13 2026 UPDATE — HY4 STATUS CHANGED, Jack asked to be told when it did

TWO SEPARATE GATES, and they now have different answers:

* ARCHITECTURE GATE: PR #28127 "Model: add Tencent Hy 4 (hy_v4) preview architecture support" (Little0o0, opened Aug 31 2026) is MERGED — GitHub shows the Merged badge, last activity Sep 6 2026. Mainline llama.cpp now supports the hy_v4 architecture. This supersedes the earlier "architecture unsupported" framing. PR discussion shows testing on Epyc 9374F CPU and RTX PRO 6000 Max-Q (CUDA ARCHS=1200, AVX2=1); NO sm_70/Volta mention, so Volta remains unverified as usual.
* QUANT-FORMAT GATE: PR #22836 (STQ1_0 ternary) is still OPEN, most recent commit Aug 10 2026 ("ggml-cpu : fix STQ1_0 CI failures"). Still ARM NEON + scalar fallback only; BlackDawnNova's AVX2 patch is in the thread but unmerged; no CUDA. So the 229.4 GB STQ1_0 file is still effectively unusable on Jack's x86 box.

THE FILE THAT CHANGES THE ANSWER: AngelSlim/Hy4-preview-GGUF (264,370 downloads) holds THREE weights files, sizes pulled live from the HF tree API Sep 13 2026:

* `Hy4-preview-Q4_K_M.gguf` 467,292,398,016 bytes (467.3 GB) — far too big
* `Hy4-preview-STQ1_0.gguf` 229,412,839,872 bytes (229.4 GB) — blocked by the open quant PR above
* `Hy4-preview-UD-IQ1_M.gguf` 235,351,974,336 bytes (235.4 GB = 219.2 GiB) — IQ1_M is a STANDARD llama.cpp quant with existing AVX2 and CUDA kernels, so it is not blocked by PR #22836 at all

FEASIBILITY OF UD-IQ1_M ON JACK'S BOX: 219.2 GiB of weights against 237 GiB available leaves only ~18 GiB for KV cache, compute buffers and margin. Fits, but with almost no room, and only with a small context and with GLM not loaded at the same time. Disk is fine (839 GB free before the GLM pull). Speed estimate: 49B active params at ~1.75 bits ≈ 10.7 GB/token, same ballpark as GLM-5.3-Flash, so ~3.5 t/s at his measured 39 GB/s ceiling — BUT i-quants are markedly more compute-hungry to dequantize than K-quants on AVX2 (he has no AVX-512), so expect materially worse, plausibly 1.5-2.5 t/s. UNMEASURED. CHEAP LOCAL CHECK OWED: `grep -ril "hy_v4\|hunyuan" ~/llama.cpp/src/ | head` — his production build b10918 postdates the Sep 6 merge, so the architecture may already be in the binary he has.

### FROM THE ACTUAL AngelSlim MODEL CARD (raw README pulled Sep 13 2026) — corrects two earlier claims

* Their build instructions pin `git checkout 0cea36222` plus TWO patches: `0001-hyv4-architecture.patch` (required for BOTH GGUFs) and `0002-stq1_0-quant-and-cuda.patch` (STQ1_0 only). So UD-IQ1_M is NOT patch-free in their instructions — but the architecture patch predates the Sep 6 merge of PR #28127, so on current mainline it should be redundant. That last step is an INFERENCE from the merge date, not stated by the card; the grep above settles it.
* CORRECTION to the earlier "no CUDA support is mentioned anywhere" claim about STQ1_0: AngelSlim's patch is named `stq1_0-quant-and-cuda`, so their version DOES include a CUDA path. The earlier claim was about the upstream PR thread and was overgeneralized to the format. Does not change Jack's outcome (he would be on CPU regardless), and the card says nothing about an AVX2 CPU kernel.
* Exact sizes AS THE CARD STATES THEM, in GiB: Q4_K_M 435.20 GiB (4.86 bpw), UD-IQ1_M 219.83 GiB (2.44 bpw), STQ1_0 213.66 GiB (2.38 bpw). The 219.83 figure matches the byte count converted earlier.
* UD-IQ1_M composition: routed-expert gate/up at 1.75 bpw (IQ1_M) plus 2.0625 bpw (IQ2_XXS) — both STANDARD llama.cpp i-quant types with existing kernels, confirming architecture is the only gate for that file. STQ1_0 composition: 1.3125 bpw STQ1_0 on 29 layers plus 2.0625 bpw IQ2_XXS on the other 48.
* THE EXPECTATION ANCHOR: the card's own benchmark for STQ1_0 is 204.56 ± 1.42 t/s prefill and 20.47 ± 0.02 t/s decode on EIGHT H20 GPUs with the model fully resident in VRAM. Roughly a terabyte of datacenter VRAM buys 20 t/s. Jack would feed it from DDR4-2133 at a measured 39 GB/s.
* CONSEQUENCE FOR THE DECISION: 219.83 GiB against 237 GiB available leaves ~17 GiB for KV and buffers — fits only at small context with nothing else large loaded. GLM-5.3-Flash is 18B active vs Hy4's 49B, so GLM is ~2.5x faster on the same memory path for a 36 GB smaller download. If GLM measures at ~3.5 t/s, Hy4 lands near ~1.3 t/s. Recommendation given Sep 13: finish and MEASURE GLM first, then decide; do not download Hy4 on the strength of benchmark tables produced on 8x H20. Other Hy4 GGUF repos found live: AMAImedia/Hy4-preview-BF16-GGUF (2,530), 6block (1,321), qtum (857), avar6 (523), anemll/Hy4-preview-FlashMoE-STQ1_0 (281).

## Sep 13 2026 — THE HEAD-TO-HEAD THAT SETTLES GLM vs HY4

Jack raised AngelSlim's quantization-loss table (MCP Atlas 83.7→83.2, SWE-Bench multi 82.9→81.3, MRCR 81.3→81.1, IFBench 73.5→72.5, i.e. ~1% loss at ~1 bit) as the case for Hy4. Two caveats on the table itself: it is measured on MIX-STQ1_0, the file that will NOT run on x86, so it is not published evidence for the runnable UD-IQ1_M; and the figures are AngelSlim's own, so [VENDOR] not [SOURCE]. Point in Jack's favour though: UD-IQ1_M is 2.44 bpw against STQ1_0's 2.38 bpw, slightly MORE bits, so quality should be comparable or marginally better.

BUT QUANTIZATION LOSS IS NOT THE BINDING QUESTION. Jack pushed back on "are you sure they're comparable", correctly — the first llm-stats check had numbers for only ONE shared benchmark and marked the rest as bare "wins", which usually means each model reported a different benchmark set. Re-checked against benchlm.ai (https://benchlm.ai/compare/glm-5-3-flash-vs-hy4-preview), which has EIGHT benchmarks scored for both:

| Benchmark | GLM-5.3-Flash | Hy4-preview | Gap |
|---|---|---|---|
| AutomationBench | 48.8 | 32.1 | GLM +16.7 |
| Toolathlon-Verified | 78.4 | 74.1 | GLM +4.3 |
| Agents' Last Exam | 26.3 | 22.8 | GLM +3.5 |
| HLE w/ tools | 55.3 | 55.4 | Hy4 +0.1 |
| DeepSWE | 63.4 | 64.3 | Hy4 +0.9 |
| Terminal-Bench 2.1 | 84.3 | 85.4 | Hy4 +1.1 |
| NL2Repo | 56.3 | 58.9 | Hy4 +2.6 |
| OfficeQA Pro | 62.4 | 66.2 | Hy4 +3.8 |

SHAPE OF THE RESULT (corrects the earlier "GLM wins 4, Hy4 wins 3"): Hy4 wins MORE benchmarks, 5 of 8, but narrowly — four of its five wins are under 3 points. GLM wins 3 but wider, carried by AutomationBench +16.7. Mean delta across all eight is +2.0 to GLM; excluding AutomationBench as an outlier it is −0.1, dead even. CONCLUSION HOLDS: they are peers.

Single-model-only scores (not comparable, and some look shaky): GLM-5.3-Flash claims LiveCodeBench 80.5, SWE-bench 92.0 (implausibly high, above frontier — distrust), GPQA Diamond 86.4, MMLU-Pro 86.1, CharXiv 89.4, MMVU 80.5. Hy4 claims SWE-bench Pro 65.7, SWE Multilingual 82.9, MCP Atlas 83.7, WideResearch 83.9, CyberGym 78.4, GPQA 92.3 AND GPQA-D 92.3 (identical figures for two different subsets — likely a data-entry conflation, distrust).

STRONGEST PRO-HY4 EVIDENCE, and it is still close: Tencent's own blind eval, 203 engineering tasks rated by 163 internal experts — Hy4 2.99 vs GLM-5.3 2.92, with 46.8% wins / 12.8% ties / 40.4% losses. That is Tencent's own people, scored against the FULL 744B GLM-5.3 rather than Flash, and Hy4 still loses 40% of exchanges.

ALL OF THE ABOVE IS [VENDOR] SELF-REPORTED, aggregated by third parties. Artificial Analysis has NO comparison page for this pairing (404), so no neutral composite index exists as of Sep 13 2026.

MARKET SIGNAL (cost, not capability): OpenRouter prices Hy4-preview at $0.834/M in and $2.501/M out against GLM-5.3-Flash at $0.075/M and $0.25/M, roughly 10x. Tracks 49B active vs 18B. OpenRouter also lists context as Hy4 1,048,576 and GLM-5.3-Flash 1,310,720. GLM-5.3-Flash card also states 321B total / 18B active, Terminal Bench 2.1 84.3, ExtractBench mean 80.75 (short 96.3, medium 51.56); the card gives no SWE-Bench/MRCR/AIME numbers.

DECISION TABLE ON JACK'S HARDWARE: GLM 18B active / 186 GiB weights / ~3.5 t/s est / ~50 GiB KV headroom, versus Hy4 UD-IQ1_M 49B active / 219.8 GiB weights / ~1.3 t/s est / ~17 GiB KV headroom and a second 235.4 GB download. Hy4 costs 2.7x the time per token and leaves a third of the context room for equal capability. HARD CONSTRAINT: they cannot coexist. 186 + 219.8 = 406 GiB against 237 GiB available, so only one big model is resident at a time. This is a choice, not an addition.

HISTORICAL (Sep 12, now partly superseded) — Hy4-preview STQ1_0 verdict was a flat NO: PR #22836 "ggml-cpu: add STQ1_0 ternary quantization with ARM NEON vec_dot kernel" is OPEN. It ships ARM NEON plus a scalar fallback only; a community AVX2 patch (BlackDawnNova) exists in the thread but is not merged, so x86 builds fall back to the generic scalar kernel. Reference numbers from that thread: ~5.5 t/s scalar vs ~34.2 t/s with the AVX2 patch — and that was on a 1.8B model, not 200B. No CUDA support is mentioned anywhere in the PR, so the GPUs would contribute nothing.

## Sep 14 2026 — JACK WANTS GLM AT 4-BIT, NOT IQ3_XXS. THE 4-BIT TO USE IS UD-IQ4_XS

"I'd want to run it at 4 bit quant." Two 4-bit-ish options exist, and the names mislead (unsloth dynamic quants vary bits per tensor, so compute bpw from the byte counts):

* UD-IQ4_XS = 156,821,710,675 bytes = 156.82 GB = 146 GiB = 3.91 bpw. THIS IS THE ONE. Against the MEASURED 209 GiB available it leaves ~63 GiB for KV and compute. Comfortable.
* UD-Q4_K_XL = 199.7 GB = 186 GiB = 4.98 bpw, i.e. effectively FIVE bits despite the Q4 name. Leaves only ~23 GiB, which is the stored swap hazard. Wrong pick on this box.

Cost of going 4-bit over IQ3_XXS: +36.45 GB of download and disk writes (156.82 vs 120.37 GB), and it crowds the RAM budget below.

### RESIDENCY vs LOADING — the distinction Jack's question exposed

He asked whether all the models would "be in queue at the same time, or could the 27b download and install models from the SATA SSD." MODELS DO NOT QUEUE. They occupy memory or they do not. What queues is REQUESTS (llama-server's `n_slots 4`). Two different resources, easy to conflate.

RAM BUDGET, against 209 GiB measured available with everything running. The 27B lives in GPU VRAM so it costs essentially no system RAM:

* router Qwen3-1.7B 1.3 GB, embeddinggemma 334 MB, Qwen3-Reranker-0.6B 639 MB — all trivial, keep resident
* GLM UD-IQ4_XS 146 GiB leaves ~63 GiB
* a resident coding model (Qwen3-Coder-Next at UD-Q3_K_XL ~36 GB / UD-Q2_K_XL ~27 GB) would take that to ~181 GiB, leaving ~28 GiB. TIGHT.
* the same two at GLM IQ3_XXS (112 GiB) + coder (~35 GiB) = 147 GiB, leaving ~62 GiB. Comfortable.

SO THE REAL COST OF 4-BIT GLM IS THAT IT CROWDS OUT A RESIDENT CODING MODEL. That is the actual tradeoff to put to Jack, not quality-per-bit.

LOAD TIME FROM DISK — the number that decides whether "standing by" is real. For CPU inference every weight is touched every token, so the whole file lands in page cache on the first pass regardless of mmap. Loading 146 GiB cold:

| medium | approx rate | cold load |
|---|---|---|
| SATA HDD | ~200 MB/s | ~13 min |
| SATA SSD | ~500 MB/s | ~5 min |
| NVMe Gen3 (his slot) | ~1.5-2 GB/s | ~1.5-2 min |

CONSEQUENCE FOR WANT 9 in jarvis-system-build: if GLM lives on a SATA HDD and is not resident, escalation is a 13-minute wait, which destroys the "ready for anything that gets flagged" premise. Resident-in-RAM is what makes instant escalation real; disk is for the library, not the working set.

ARCHITECTURE ANSWER: working set (things needed instantly) stays RAM-resident; the LIBRARY of models not currently in use lives on the bulk SATA drive; on-demand loads accept the load-time penalty above. And YES the 27B can manage this itself — downloading and swapping models is just another job type, and the supervisor's slot registry with `-hf` already does the mechanics — but a 150 GB download is a large disk write and should be gated on Jack's approval, not autonomous.

## Sep 14 2026 — RUNNABLE-QUANT HEAD TO HEAD. THIS IS THE COMPARISON THAT DECIDES IT

Comparing the models at full precision was the wrong frame. What matters is the best quant each can actually run on 251 GiB of RAM with 209 GiB measured available (27B + Open WebUI + browser tools + supervisor + embedding server all running). AngelSlim/Hy4-preview-GGUF (264,370 downloads) contains only THREE files, all size-verified live from the HF tree API:

* `Hy4-preview-Q4_K_M.gguf` — 467,292,398,016 bytes = 467.3 GB. Impossible, nearly 2x his total RAM.
* `Hy4-preview-STQ1_0.gguf` — 229,412,839,872 bytes = 229.4 GB. Needs BOTH unmerged PRs (#22836 base, #27377 x86 AVX2) and lands on the scalar path without the second. See jarvis-incidents.
* `Hy4-preview-UD-IQ1_M.gguf` — 235,351,974,336 bytes = 235.4 GB = 219.2 GiB.

There is NO unsloth Hy4 repo (401). Other repos are tiny by downloads: qtum 857, AMAImedia BF16 2,530, avar6 523, 6block 1,321.

THE DECIDING FACT: Hy4 UD-IQ1_M at 219.2 GiB does NOT FIT in the 209 GiB available. To load it Jack would have to shut down the 27B and everything else, leaving ~26 GiB of the 251 GiB total for KV and compute buffers. That is both painfully tight and exactly the "kill the model I am running to load the model I want" self-termination pattern banned in the Jarvis operating manual.

| | GLM-5.3-Flash | Hy4-preview |
|---|---|---|
| Best runnable quant | UD-IQ3_XXS 120.37 GB / 112 GiB | UD-IQ1_M 235.4 GB / 219.2 GiB |
| Bits per weight | 3.00 (120.37e9 x 8 / 320.76e9) | 2.44 (~772B total implied) |
| Fits beside the running 27B? | YES, ~97 GiB spare | NO |
| Active params | 18B | 49B |
| Est. read per token | ~6-7 GB | ~15 GB |
| Est. speed at his MEASURED 38-39 GB/s | 3-5 t/s | ~1.3-2.5 t/s |
| Download / drive writes | 120 GB | 235 GB |
| Software state | 1 unmerged PR, ALREADY BUILT at ~/glm5-llama.cpp | 2 unmerged PRs, not built |

CONCLUSION: GLM wins on every axis at the quants that actually run. It gets 23% more bits per weight (3.00 vs 2.44), fits with 97 GiB to spare instead of not fitting, downloads half as much onto the drive under investigation, and runs 2-4x faster. The Sep 13 note that they are "peers" was true of full-precision benchmark tables and is NOT true of what this box can execute. Do not revisit Hy4 unless RAM grows past ~300 GiB or a much smaller Hy4 quant is published.

## Sep 14 2026 — NEUTRAL COMPOSITE INDEX NOW EXISTS, and it partly overturns the "nothing is meaningfully smarter" line

The Sep 13 note said no neutral composite existed for this pairing. Artificial Analysis DOES now carry both models separately, on Intelligence Index v4.3 (same ten evals both sides: AA-Briefcase, GDPval-AA v2, AutomationBench-AA, Terminal-Bench v4.0, SciCode, Humanity's Last Exam, GDP.pdf, CritPt, AA-Omniscience, AA-LCR v1.1):

* GLM-5.3-Flash: 42. 180M output tokens on the index run vs a 130M median, i.e. notably verbose. Provider output speed 107.4 t/s, TTFT 2.42 s.
* Qwen3.8-27B (xhigh): 34. 200M output tokens vs a 76M median, so even MORE verbose. Provider output speed 42.7 t/s.
* Qwen3.8-27B (non-reasoning): 22.

So on the same index version GLM-5.3-Flash is +8 over the 27B Jack runs today. That is a real capability gain, not noise.

CORRECTION TO A STALE NUMBER: the "41 vs 57 on AA index" figure carried in local-ai-setup for Qwen3.8-27B, and Simon Willison's Aug 17 2026 headline "Qwen 3.8 27B scores 52" (which matched GPT-5.6 Luna (max) and sat one point behind GLM-5.2 (max) and DeepSeek V4 Pro), are from EARLIER index versions. AA re-baselines and scores fall when harder evals are added. Do not mix versions: only compare numbers drawn from the same stated index version.

THE THREE THINGS THAT EAT THAT +8 ON JACK'S BOX:

1. The 42 is full precision on a provider's hardware. Jack would run UD-IQ3_XXS at ~3.0 bpw. No published eval exists at that quant, so the delivered number is unknown and certainly lower than 42. His 27B runs Q4_K_M, a milder quant, so it is less degraded from its 34. The gap narrows by an unmeasured amount.
2. Speed: 32 t/s MEASURED today vs 3-5 t/s ESTIMATED for GLM. Roughly 8x slower.
3. GLM-5.3-Flash is a REASONING model and `reasoning_effort` defaults to `max` (levels: low / high / max). Thinking can be turned off with `clear_thinking=false` in the chat template, or dialled down with reasoning_effort. Left at default, a 3,000-token thinking block at 3-5 t/s is 10-17 minutes BEFORE the answer starts.

Card-stated scores for GLM-5.3-Flash (zai-org HF): 320B total / 18B active, 300K context for evaluation, Deep SWE 63.4, Terminal Bench 2.1 84.3, ParseBench mean 70.75 (text content 88.34, text formatting 79.49).

PRACTICAL CONCLUSION: GLM-5.3-Flash is NOT a replacement for the 27B, it is a second slot for batch work — queued deep research, long code generation, document analysis where nobody is waiting — while the 27B keeps every interactive and agentic job. This is exactly the split the supervisor in jarvis-orchestrator exists to make, so the orchestrator work done Sep 14 is what makes GLM usable at all rather than merely present.

SUPERSEDED IN PART: Qwen3.8-27B Q4_K_M at the measured 32 t/s remains the most capable thing Jack can run INTERACTIVELY. Nothing in the 32GB class is meaningfully smarter, because the ceiling is VRAM, not model choice. Re-check these two PRs for "merged" status before revisiting; the merge alone is not sufficient, sm_70 kernel support has to be confirmed separately.

## Sep 21 2026 — RAM PURCHASED, AND THE TARGET IS FULL GLM-5.3, NOT FLASH

Jack bought 8 more 32GB DDR4 sticks (256 GB additional) for the ESC4000, explicitly to run GLM-5.3. When asked, he confirmed he means the full GLM-5.3, not GLM-5.3-Flash. This invalidates the memory arithmetic throughout this file, which is all computed against 251 GiB total / 209 GiB available. Recompute every fit verdict before reusing it — including "Hy4 UD-IQ1_M does not fit", the GLM-vs-coder crowding tradeoff, and the swap hazard note in nvme-drive-failure.

NOT YET VERIFIED, and needed before the sticks go in: the exact part number on one NEW stick and one ALREADY-INSTALLED stick. The Z10PG-D16 will not run LRDIMM and RDIMM together, mixed speeds clock down to the slowest stick, and populating all 16 slots typically drops the memory clock. NOT YET VERIFIED for the full GLM-5.3: per-file weight sizes were never pulled. The 186 GiB figure carried in earlier notes is FLASH's, not the full model's. The full model's recorded quants here are UD-IQ1_S ~217 GB and UD-IQ2_M 239 GB, so disk space on the 931 GB boot drive may bind before RAM does. Pull live sizes from the HF tree API before any download.

SEQUENCING [stated]: sticks stay in the box until the Sept 2026 restore is finished and jarvis-1 boots reliably — one variable at a time. GLM-5.3 remains on hold per Jack's restore runbook until he says otherwise.

## Sep 21 2026 — RAM IS IN AND VERIFIED. 503 GiB TOTAL. SUPERSEDES THE "NOT YET VERIFIED" ITEMS ABOVE

The sticks were installed (not held back as sequenced above) and the machine POSTed with all 16 slots populated. Measured on the freshly installed Ubuntu 24.04:

* `free -g`: total 503 GiB, swap 7 GiB. (16 x 32 GB = 512 GB raw; 503 GiB reported is normal overhead.)
* `dmidecode -t memory`: all 16 Part Numbers IDENTICAL — M393A4K40BB0-CPB. No RDIMM/LRDIMM mixing, no reseat needed, the compatibility risk flagged above is closed.
* Rated `Speed: 2133 MT/s` on all 16; `Configured Memory Speed: 1866 MT/s` on all 16. That is the expected 2-DIMM-per-channel downclock on the Z10PG-D16, 87.5% of rated, so ~12.5% memory bandwidth lost in exchange for 2x capacity. Board-level behaviour, not fixable by reseating.

CONSEQUENCE: every fit verdict in this file computed against 251 GiB total / 209 GiB available is now wrong and must be recomputed against ~503 GiB. Also recompute the measured 38-39 GB/s throughput ceiling — it was taken at 2133 and should be scaled by roughly 0.875 before use in any t/s estimate.

## FINAL WRITE — Sep 21 2026 — REBUILT BOX (Samsung 990 PRO, fresh Ubuntu 24.04), llama-server VERIFIED SERVING [MEASURED]

Build b11089-f4e276a20, driver 580.178.04, CUDA 12.9, sm_70. Unit: /etc/systemd/system/llama-server.service, user simon, `-hf ggml-org/Qwen3.8-27B-GGUF:Q4_K_M -ngl 99 -sm layer -ctk q8_0 -ctv q8_0 -c 8192 --host 0.0.0.0 --port 8080 --jinja`, Environment=GGML_CUDA_DISABLE_GRAPHS=1, Restart=always/RestartSec=3, After=network.target nvidia-powercap.service.

* SERVES. /v1/models answers; real /v1/chat/completions returned correct content. Model meta: n_params 26,895,998,464, size 18,962,876,416 B (17.66 GiB), n_embd 5120, n_vocab 248320, n_ctx_train 262144, n_ctx 8192. n_slots=4, n_ctx_slot=8192, kv_unified=true.
* MEASURED Sep 21 on the live service: generation 28.09 t/s (152 tok), prompt 102.58 t/s — but prompt figure is from a 68-token prompt, so it is overhead-dominated and NOT comparable to the 145.8 t/s baseline. Generation is comparable: 32.0 (Sep 12) -> 28.09, a ~12% drop.
* VRAM [MEASURED]: GPU0 15,078 / 16,384 MiB, GPU1 10,266 / 16,384 MiB. Power cap 200 W + persistence Enabled live on both. clocks.current.memory 877 MHz, confirming the 1866 MT/s downclock.
* THE 4.8 GiB CARD IMBALANCE IS THE VISION ENCODER, NOT THE KV CACHE. The model auto-loads mmproj-Qwen3.8-27B-Q8_0.gguf. With FA compiled out (-DGGML_CUDA_FA=OFF), the CLIP graph must materialize a full attention matrix: warmup logs `SOFT_MAX: type = f32, ne = [8464 8464 16 1]` = 8464×8464×16×4 B = 4.27 GiB. Matches the OOM-loop allocation `4657.81 MiB on device 0` and the measured 4,812 MiB imbalance.
* CONSEQUENCE: GPU0 has only ~1.3 GiB free. Raising -c is IMPOSSIBLE until FA is rebuilt; with Restart=always it would reproduce the crash loop. The FA rebuild is the unlock for larger context, not just a speed item.
* CORRECTION TO WATCH FOR: the warmup lines "flash attention not supported by CUDA0" / "flash attention is disabled" are emitted inside the CLIP-graph warning block and are scoped to the VISION graph. They are evidence the build lacks FA kernels; they are NOT a readout on the text KV cache.
* STILL UNRESOLVED: whether -ctk/-ctv q8_0 are honoured or silently downgraded. Verbosity is 3 and llama.cpp printed NO llama_kv_cache / KV-buffer-size lines at all in 59 journal lines, so the log cannot answer it. A/B test (restart with -ctk f16 -ctv f16, diff total VRAM) is designed but NOT run — unsafe while GPU0 has 1.3 GiB free.
* OOM HISTORY RESOLVED: the 17:12-17:13 restart loop was the stray llama-cli holding 12.6/12.5 GB. First start after the GPU was freed (17:14:26) loaded clean.
* SECURITY NOTE [not yet addressed]: no API key, CORS allows all origins, bound 0.0.0.0 — reachable by anything on the tailnet.
* `graphs reused = 151` appears despite GGML_CUDA_DISABLE_GRAPHS=1; that counter is ggml scheduler graph reuse, a different thing from CUDA graphs. Do not read it as proof CUDA graphs are on.

## Sep 21 2026 (later) — FA AND KV QUESTIONS, MEASURED. Corrects the "unresolved" note above.

* MODEL GEOMETRY [MEASURED, gguf_dump on Qwen3.8-27B-Q4_K_M]: arch key prefix `qwen35`. block_count 64, embedding_length 5120, attention.head_count 24, attention.head_count_kv 4, attention.key_length 256, attention.value_length 256, rope.freq_base 1e7, rope.dimension_count 64. KV per token = 64*(4×256 K + 4×256 V) = 131,072 elements => f16 2,048 MiB @8192 ctx, q8_0 1,088 MiB @8192 ctx.
* FILE SIZES [MEASURED]: Qwen3.8-27B-Q4_K_M.gguf 18,095 MiB; mmproj-Qwen3.8-27B-Q8_0.gguf 601 MiB.
* FLASH ATTENTION IS DEFINITIVELY COMPILED OUT. `test-backend-ops support -o FLASH_ATTN_EXT` reports CUDA0 NOT SUPPORTED for EVERY variant: hsk/hsv 64, 128 and 256, and type_K/type_V f16, q8_0 and q4_0 alike. So the `fattn-*.cu.o` objects found in the build dir are STALE leftovers from an earlier configure, not proof FA is present. Two theories were tested and REFUTED: (a) that a dedicated Volta WMMA FA kernel exists — there is no fattn-wmma-f16.cu in tree at f4e276a20, only fattn.cu / fattn-tile.cu plus fattn-mma-f16 instances, so FA on sm_70 would dispatch through tile/vec, weakening the SPEED case for rebuilding; (b) that the CLIP failure was a missing head-dim-72 kernel — no, CUDA0 refuses all head dims.
* THE GUARD (llama-context.cpp ~line 3732): quantized type_v with flash_attn_type AUTO force-sets FA to ENABLED; it only hard-errors when FA was explicitly DISABLED. The unit passes no -fa, so it took AUTO and did not abort. CONSEQUENCE: llama.cpp likely ran a quantized V cache with FA subsequently disabled at warmup, i.e. the state the guard exists to prevent. NOT yet proven either way.
* STILL OPEN: whether type_v stayed q8_0 or was silently downgraded to f16. VRAM subtraction favours q8_0 (GPU0 has only ~764 MiB left after weights+mmproj+CLIP workspace, and half an f16 cache is 1,024 MiB) but the compute-buffer term was assumed, not measured, and with FA off the TEXT attention also materializes softmax matrices, so that term was likely underestimated. Do not treat q8_0 as confirmed.
* LOGGING DEAD END, do not repeat it: llama.cpp CORE log lines (llama_model_loader, print_info, load_tensors, llama_kv_cache / KV buffer size) DO NOT APPEAR AT ALL in this build at verbosity 3 — not in journald and not in a foreground run redirected to a file (60 lines, server-layer and warmup only). The line stating type_k/type_v was never emitted. Next step if resumed: `-lv 9`, and if that still yields nothing, stop reading and measure by running the same config twice (q8_0 vs f16) and diffing peak VRAM.
* SAFE FOREGROUND TEST HARNESS THAT WORKED (no strays, no pkill): `sudo systemctl stop llama-server; sleep 3;` then `GGML_CUDA_DISABLE_GRAPHS=1 timeout 60 llama-server <same flags> --host 127.0.0.1 --port 8081 > /tmp/log 2>&1;` then `sudo systemctl start llama-server`. timeout bounds it, separate port avoids collision, GPUs verified at 0 MiB after the stop.
* Sep 21: Jack called a halt to this diagnostic thread — "i just want to be able to talk to the model and have it use run_host_commands on openwebui". Priority order he set: get Open WebUI chatting with the model first, then resume the VRAM/FA work. The server was already serving at 28 t/s throughout; none of the above blocked him.

## Sep 21 2026 — SPEED RESEARCH FOR Qwen3.8-27B ON 2x V100. THE ANSWER IS MTP.

Model geometry [MEASURED from GGUF]: arch qwen35, n_layer 64, n_head 24, n_head_kv 4, n_embd_head_k/v = 256, n_ff 17408, n_expert 0 (DENSE), n_swa 0, mrope sections [11,11,10,0], n_vocab 248320, n_ctx_train 262144. HYBRID: `qwen35.attention.recurrent_layers` = 3 recurrent (SSM: ssm_d_state 128, ssm_d_inner 6144, ssm_n_group 16) then 1 full-attention, repeating. So only 16 of 64 layers hold a growing KV cache — context is CHEAP (q8_0 KV at 8192 ctx ≈ 272 MiB).

* MTP IS THE 60-70 t/s MECHANISM Jack remembers. llama.cpp b11089 `--spec-type` accepts: none, draft-simple, draft-eagle3, draft-mtp, draft-dflash, draft-dspark, ngram-simple, ngram-map-k, ngram-map-k4v, ngram-mod, ngram-cache. Added by PR #22673 (July 2026).
* THE GATE: the ggml-org GGUF Jack runs has NO MTP head. Per sudoingX/qwen38-mtp, the `blk.*.nextn.*` tensors ship in unsloth's and Jackrong's Qwen3.8-27B GGUFs, NOT ggml-org's; llama.cpp loads and ignores them without the flag. Jack's print_info shows no n_layer_nextn.
* RECIPE: `--spec-type draft-mtp --spec-draft-n-max 2 --parallel 1` (single slot MANDATORY), with `-fa 1 --cache-type-k q4_0 --cache-type-v q4_0 -ngl 999`.
* GAINS [SOURCE, not Jack's box]: RTX 3090 31.0 -> 41.3 t/s (+33%); RTX 5090 mobile 36.7 -> 50.9 t/s (+39%). Acceptance 0.76-0.82. Jackrong's card claims ~2x throughput [VENDOR].
* Jackrong/Qwen3.8-27B-MTP-GGUF quants: Q2_K 10.9GB, Q3_K_M 13.5, IQ4_XS 15.4, Q4_K_S 15.8, Q4_K_M 16.8GB, Q5_K_M 19.5, Q6_K 22.4, Q8_0 29.

-sm tensor IS BROKEN ON V100. DO NOT RECOMMEND IT. llama.cpp issue #27366 (OPEN, vs commit 9731ad3f2, Aug 18 2026): `-sm tensor` on multi-GPU Volta asserts or hangs while leaking VRAM. `-sm row` unavailable on CUDA at all ("device CUDA1 does not support split buffers"; SYCL only). `-sm layer` is the only working mode, and costs little: that issue shows pp4096 777.09 split vs 774.81 single-GPU.

FLASH ATTENTION ON sm70: HELPS PREFILL, NOT DECODE. fishlikeX/sm70-attn (V100 fork: D256 kernels, SplitKV3, q4_0 in-kernel KV, DFlash2 spec decoding), 1x V100 Qwen3.8-27B Q4_K_XL: 176k prefill 521.93 t/s vs stock 372.94 (+39.9%), but 8k decode 29.06 ≈ stock. Decode is bandwidth-limited by reading WEIGHTS, not attention. Upstream PR #27997 adds an sm70 FA config for exactly DKQ=256/DV=256 (Jack's head dim) — still DRAFT, unmerged as of Sep 3 2026; claims +27.84% prefill, and amgomez measured +11.6% @71k / +17.2% @122k on 2x V100-SXM2.

* V100 DATA POINT: kvmem issue #24, 2x V100-SXM2-16GB, Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf, CUDA 12.6, `CMAKE_CUDA_ARCHITECTURES=70-real -DGGML_CUDA_FA_ALL_QUANTS=ON`: decode 47.3 t/s, 48K prefill ≈464 t/s, 14.1 GiB VRAM. That file is IQ3_S (smaller/faster than Q4_K_M) AND mtp.
* BANDWIDTH CEILING for Jack's box: 18.1 GB of weights per token / 900 GB/s HBM2 = ~20 ms = ~50 t/s hard ceiling without speculation. Measured 28.09 t/s = 35.6 ms/token ≈ 56% efficiency. Non-speculative tuning can plausibly reach 35-40, NOT 60-70. Past ~50 REQUIRES speculation.
* ngram-mod [MEASURED on Jack's box Sep 21]: no gain. Short prompt 28.10 vs 28.09 baseline; copy-heavy 506-token prompt 20.28 t/s generation (NOT a clean A/B, context length differed). Prompt processing on that 506-token prompt measured 300.95 t/s, superseding the 145.8 "baseline" and confirming 102 t/s was per-request overhead on 68 tokens.

## Sep 22 2026 — RECOMPUTED AGAINST 503 GiB RAM, PLUS A NEW MODEL (MiMo-V2.6-Pro) AND A KEY CORRECTION ON GLM-5.3

Jack asked whether he can run GLM-5.3, GLM-5.3-Flash, Hy4-preview or MiMo-V2.6-Pro. Researched fresh via web search/fetch (GitHub PR pages, HF file trees, and 3+ independent blog writeups per claim where possible), not just extrapolated from the Sep 12-14 notes above, because RAM changed (251→503 GiB) and time has passed on the open PRs.

CORRECTION TO EARLIER FRAMING: full GLM-5.3 is NOT blocked like Flash is. Two independent Sep 5-6 2026 sources (dev.to "the llama.cpp surprise" writeup, modemguides.com) agree: GLM-5.3 (the 744B/40B-active flagship) uses the `glm-dsa` architecture, which llama.cpp has supported since GLM-5.2 — it runs on Jack's STOCK build today. Only GLM-5.3-Flash (320B/18B-active) uses the new hybrid `glm5next`/KDA architecture that is still unmerged. The two models were wrongly treated as sharing one fate in the Sep 12-14 notes above; they don't.

GLM-5.3 (full, unsloth/GLM-5.3-GGUF, sizes cross-checked HF tree + modemguides, both agree): UD-IQ1_S 216.7GB/202 GiB, UD-IQ1_M 228.5GB/213 GiB, UD-Q2_K_XL 253.9GB/236 GiB, UD-Q3_K_XL 343.0GB/319 GiB (3.69 bpw), UD-Q4_K_XL 467.3GB/435 GiB (5.02 bpw despite the "Q4" name, same dynamic-quant mislabeling pattern as Flash). RUNS TODAY, no architecture gate. Fit against 503 GiB total: everything through Q3_K_XL fits with well over 100 GiB of KV/compute headroom; Q4_K_XL at 435 GiB is TIGHT (~15-65 GiB spare depending on what else is resident — re-measure `free -g` before trying it, same swap-hazard pattern flagged for Flash's Q4_K_XL earlier in this file). Speed UNMEASURED: 40B active params at ~33-34 GB/s effective bandwidth (the measured 38-39 GB/s scaled by the 1866/2133 MT/s downclock) implies roughly 1.8 t/s at Q3_K_XL, ~2.7 t/s at IQ1_M — same ballpark as Hy4/MiMo below since all three have similar active-param counts. License: custom "GLM-5.3 License", individuals get effectively MIT terms (per Sep 12 note above).

GLM-5.3-Flash: STILL NOT MERGED to mainline as of the latest checks (Sep 3-20 2026 sources). Three competing PRs remain open: #27754 (danielhanchen/unsloth), #27752 (eauchs), #27773 (timkhronos) — most recent activity found was Aug 30, no maintainer merge. codersera.com (checked against Aug 31) explicitly: "Upstream llama.cpp does not support GLM-5.3-Flash yet... three competing support PRs have been open since 26 August," workaround is building Unsloth's fork or PR #27773 directly. Sizes unchanged from Sep 13-14 notes (UD-Q4_K_XL 199.7GB/186 GiB now trivially fits in 503 GiB with ~260+ GiB spare). If Jack wants Flash specifically, the move is building the patched fork, not waiting on stock — but full GLM-5.3 above needs no such workaround and is arguably the easier win now.

Hy4-preview: 770B total / 49B active (vettedconsumer.com, corroborates memory's 744-ish ballpark for GLM being separate). Architecture (`hy_v4`) CONFIRMED MERGED — both the PR page and a llama.cpp 0.4.1 release-notes writeup (freedom.tech, Sep 14 2026) list "Tencent Hy 4 (hy_v4) preview architecture support" as shipped. UD-IQ1_M 235.4GB/219.2 GiB now fits with ~230 GiB spare (previously didn't fit in 209 GiB — that constraint is gone). STQ1_0 (229.4GB) UNCHANGED: still gated on the separate ternary-quant PR, x86 has only a scalar fallback (no AVX2/CUDA merged upstream), not worth using on Jack's Haswell box. Speed UNMEASURED: 49B active ≈ 2.2 t/s estimate at his effective bandwidth, slightly slower than GLM-5.3-full or MiMo below because it has the most active params of the three.

NEW: MiMo-V2.6-Pro (Xiaomi), just released Sep 21-22 2026 — 1.02T total / ~42B active MoE, MIT license, natively omnimodal (text/image/video/audio), 1M context, "five-layer" MTP module for speculative decoding, trained via RL (~750K trajectories, <6 days). Scored 46.32 on Artificial Analysis Intelligence Index v4.3 — HIGHEST of any open-weights model on that index as of release, per Artificial Analysis's own announcement (their claim, [VENDOR/neutral-index hybrid] — AA runs the index but Xiaomi supplied the model). DeepSWE v1.1 72.6. Architecture support: the base MiMo-V2 family (`mimo2` in llama.cpp source, e.g. `src/models/mimo2.cpp`) merged via PR #22493 against the V2.5 release; V2.6 is the same total/active param count as V2.5-Pro, so it's very likely the same architecture with updated RL weights — reasonably high confidence it loads on Jack's current build, but UNCONFIRMED for V2.6 specifically since it just shipped and no V2.6 GGUF was found yet (only unsloth/MiMo-V2.5-Pro-GGUF, MiMo-V2.5-GGUF, MiMo-V2-Flash-GGUF exist as of this research). A follow-up PR for missing Flash Attention kernels was still pending as of the V2.5 merge, and vision support sits on an unmerged branch — neither blocks base text inference, which is CPU-bound on Jack's box anyway. Sizes (from unsloth/MiMo-V2.5-Pro-GGUF as the best size proxy, since V2.6-Pro's own GGUF doesn't exist yet): UD-IQ1_M 304GB/283 GiB (SMALLEST), UD-IQ2_XXS/IQ2_M ~317GB/295 GiB, UD-Q2_K_XL 338GB/315 GiB, UD-IQ3_XXS 413GB/385 GiB. This fits 503 GiB with the MOST headroom of any of the four models — ~165-220 GiB spare even at IQ1_M, comfortably clear of the Q4-tier swap hazard the other three hit. Speed UNMEASURED: 42B active ≈ 2.6 t/s estimate at Jack's bandwidth, middle of the three big-MoE options.

BOTTOM LINE, all four, against 503 GiB RAM / 32 GiB VRAM (already fully used by the resident Qwen3.8-27B judge):

| Model | Runs on stock build today? | Smallest usable quant | Fits 503 GiB? | Est. decode speed |
|---|---|---|---|---|
| GLM-5.3 (full) | YES (glm-dsa, supported since 5.2) | IQ1_S 202 GiB | yes, huge headroom | ~2.7 t/s (IQ1_M) |
| GLM-5.3-Flash | NO — 3 PRs open, unmerged | Q4_K_XL 186 GiB | yes | ~3.5-5 t/s |
| Hy4-preview | YES for IQ1_M (arch merged Aug31/Sep6); STQ1_0 still blocked | UD-IQ1_M 219 GiB | yes, was previously the one that didn't fit — now does | ~2.2 t/s |
| MiMo-V2.6-Pro | LIKELY (base arch merged for V2.5, V2.6 unconfirmed, no GGUF exists yet) | UD-IQ1_M ~283 GiB (V2.5 proxy) | yes, most headroom of the four | ~2.6 t/s (estimate) |

None of these will feel fast — they're all CPU-RAM-bound at 1.3-5 t/s versus the 27B's 28-83 t/s on GPU. They are batch/overnight-job models, not interactive ones, same conclusion as the Sep 14 note on GLM-5.3-Flash above, and it now applies to all four. GLM-5.3 (full) is the one clear "yes, works today" among the three big options with no PR to wait on; MiMo-V2.6-Pro is the one with the best RAM headroom but needs a quant published first, and its own architecture merge unconfirmed for V2.6 specifically.

FREE CHECKS OWED before downloading any of these (same method as the Sep 13 GLM/Hy4 check): `grep -ril "glm5next\|mimo2\|hy_v4" ~/llama.cpp/src/` on Jack's actual build to confirm what's really compiled in, and `free -g` to get a real "available" number against 503 GiB rather than the ~450 GiB estimate used above (scaled from the old 209-237/251 GiB ratio, NOT measured fresh). Speeds above are ALL estimates, none measured — same caveat this file has applied throughout: distrust vendor/blog t/s numbers, measure on the actual box.

Sources checked this pass: github.com/ggml-org/llama.cpp PRs #27754, #27752, #27773, #28127, #22493, issue #22469, discussion #28203; huggingface.co unsloth/MiMo-V2.5-Pro-GGUF, XiaomiMiMo/MiMo-V2.6-Pro-RL; dev.to/purpledoubled GLM-5.3 writeup; modemguides.com, codersera.com, vettedconsumer.com, freedom.tech (llama.cpp 0.4.1 notes); kucoin.com and testingcatalog.com on the MiMo-V2.6 launch; artificialanalysis.ai MiMo-V2.6-Pro page.
