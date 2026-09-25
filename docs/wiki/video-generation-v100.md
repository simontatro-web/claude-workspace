# video-generation-v100

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 23, 2026).
> Cowork-only links kept as page names.
>
> Summary: Whether and how local AI video generation runs on Jack's 2x Tesla V100 16GB (Volta sm_70) — the PyTorch/CUDA cutoff, the FP16 overflow trap, the V100-specific ComfyUI projects, measured V100 render times, and which video models fit 16GB. Read before any local video-generation or auto-posting work on jarvis-1.

Researched Sep 22 2026 after Jack said video generation must be LOCAL ONLY on jarvis-1 (he chose that over an API path). Related: local-model-landscape (Volta constraints), gpu-upgrade-options (why not to buy a new card), orchestrator-slot-plan. Verified claims below survived a blind-agent check Sep 22 2026.

## THE HEADLINE: YES, IT WORKS. IT IS SLOW BUT USABLE FOR SCHEDULED BATCH POSTING.

[MEASURED, Lon.TV Sep 8 2026, on a Tesla V100 — note that review used the 32GB V100, Jack has 16GB cards]

- 5-second 720p video with LTX 2.5: ~3.5 minutes. (Same clip on a modern Intel card: under 1.5 min.)
- Single 1024x1024 Flux image: ~1 minute.
- MiniMax H3 was judged "too slow to be usable" on the V100. Reviewer's conclusion: the V100 handles current LANGUAGE models well but "may not support the next generation of multimodal AI tools as effectively." CONSEQUENCE FOR JACK: 3.5 min/clip means a scheduled overnight job can produce ~15-20 short clips a night on one card. That is plenty for an auto-posting cadence. It is NOT interactive iteration.

## *** THE THREE HARD CONSTRAINTS, IN ORDER ***

### 1. PyTorch: MUST USE THE cu126 WHEEL. [VERIFIED, pytorch/pytorch issue #172351]

PyTorch 2.11 drops Volta/sm_70 from its CUDA 12.8.1 and 13.0.0 binaries. The CUDA 12.6.3 build still lists Volta (7.0). Stated reason: keeping Volta blocks a cuDNN update, and cuDNN dropped Volta. So: install the cu126 wheel, and PIN it. Installing "latest PyTorch" produces a box where ComfyUI throws "no kernel image is available for execution on the device". This is the exact same trap already documented for the CUDA toolkit in local-model-landscape (must be 12.9 or older), one layer up.

### 2. NO BF16 ON VOLTA, AND FP16 OVERFLOWS ON SOME VIDEO MODELS. [VERIFIED, Comfy-Org/ComfyUI issue #15262]

V100 has 1st-gen tensor cores: FP16 in, FP32 accumulate, no BF16. Modern video models are trained and shipped in BF16. Casting BF16 -> FP16 is not always safe:

- MiniMax H3 on a Tesla V100 16GB produces NaN/Inf because its residual stream reaches ~1e6-1e7 while FP16 maxes at 65,504. Instant overflow.
- Secondary failure: ComfyUI's dynamic VRAM weight paging can free memory while kernels still reference it, producing garbage bit patterns that look like NaN.
- Workarounds that work: (a) FP32 compute — stable but ~8x slower than FP16 theoretical; (b) launch with --disable-dynamic-vram — costs ~30%; (c) the community ComfyUI-MiniMaxH3-FP16Safe plugin, which applies precision scaling/isolation to make FP16 viable.
- GENERAL RULE TO CARRY: before committing to any video model on this box, run one short render and check for NaN/black output. The failure is silent-ish and model-specific, not a blanket Volta problem — LTX and Flux both worked in the Lon.TV test.

### 3. 16GB PER CARD IS THE BINDING SIZE LIMIT, AND -sm-style splitting does NOT exist for diffusion

llama.cpp can split an LLM across both cards. ComfyUI generally cannot split a diffusion transformer the same way, so each video model must fit one 16GB card (plus sequential text-encoder offload).

- LTX 2.5: "No official LTX 2.5 checkpoint fits 16 GB." Smallest official combo is NVFP4 distilled transformer 18.72 GB + INT8 Gemma 4 encoder 15.37 GB ~= 34 GB, wants 24 GB+. 16GB requires the community GGUF path: ComfyUI-GGUF custom node, LTX-2.5-Distilled transformer Q3_K_S 12.65 GB through Q8_0 23.60 GB, plus gemma4-12b-with-proj-ltx-2.5 GGUF encoders 5.96-9.51 GB. Transformer + encoder exceed 16 GiB together, so the encoder must be loaded, run, then unloaded before the transformer loads.
- LTX 2.3 (unsloth/LTX-2.3-GGUF): Q2_K ~7.94-10.9 GB, Q4_K_M ~14.2-16.5 GB, BF16/F16 42 GB. Q2_K/Q3 is the comfortable 16GB target. Easier first attempt than 2.5.
- Wan 2.1/2.2 with GGUF quants is the other mainstream 16GB-capable option.

## V100-SPECIFIC TOOLING THAT EXISTS (someone has already done this work)

- NetVoobrazhenia/ComfyUI_Flash-Attention_v100 — a ComfyUI custom node enabling Flash Attention on GPUs below compute capability 8.0 (V100, T4). Detects and supports checkpoint, diffusion, clip, ltxv, flux and qwen model types, auto-converting tensor layouts. Requires the separate flash_attn_v100 library, CUDA 11.8+, Python 3.10+. Needs FP16, zero dropout, matching Q/K head counts. No published speedup numbers.
- rwashy/H3-V100 — ComfyUI MiniMax H3 inference optimizations specifically for SM70. Keeps FP32 for residual-sensitive/text-prepath/audio-query work while using FP16 for validated QKV/attention/MLP "islands"; Flash Attention or a sparse Sol-Attn backend; adaptive MLP chunk sizing. Reported on a single V100 16GB: 8-step, 24,792-token workflow, cold 563.77 s, warm ~490.84 s (~55.4 s/step). Generates video WITH audio. Recommends ~0.2-0.5 megapixels at 5-10 seconds. Tested on Windows/PyTorch 2.8.0/CUDA 12.8 — Jack is Linux and should use cu126, so this is a reference implementation, not a drop-in.
- deepbeepmeep/Wan2GP — "video generator for the GPU poor," runs select models in as little as 6 GB VRAM, supports Wan 2.1/2.2, MiniMax H3, LTX-2 (2.3-2.5), Hunyuan Video, Bernini 14B, Kandinsky. Documents GTX 10xx (Pascal) through RTX 50xx. Does NOT explicitly mention Volta/V100 — Volta is newer than the oldest supported card, so it should work, but this is inference, not a stated guarantee. Publishes no generation times for low-end hardware.

## RECOMMENDED FIRST BUILD (not yet attempted)

- Fresh venv, pip install torch --index-url https://download.pytorch.org/whl/cu126. Pin it. Verify torch.cuda.get_device_capability() returns (7, 0) and a trivial matmul runs.
- ComfyUI + ComfyUI-GGUF node. Start with LTX 2.3 GGUF at Q3/Q4_K_M on ONE card (CUDA_VISIBLE_DEVICES to pick), not LTX 2.5 — smaller, and it avoids the encoder-doesn't-fit dance.
- First render: 5s, 480p, few steps. Check for NaN/black frames BEFORE tuning anything.
- Only then add ComfyUI_Flash-Attention_v100 and measure the delta.
- Drive it headless from the job queue: ComfyUI has an HTTP API; a worker submits a workflow JSON and polls. This slots into the existing jarvis job/worker/notifier stack in jarvis-orchestrator as a new job type.

## THE POSTING HALF IS A SEPARATE PROBLEM AND IS NOT SOLVED HERE

Auto-posting needs platform API access, not GPU work: TikTok's Content Posting API requires developer registration and app approval, and unaudited apps are restricted (posts land as drafts / private until audited). YouTube Data API v3 upload has a hard quota cost of 1600 units per upload against a default 10,000/day, i.e. ~6 uploads/day before requesting a quota increase. Both need OAuth tokens stored on the box. NOT researched in depth yet — flagged so the "fully automatic" goal is not assumed to be free. Open-source pipeline references found but not evaluated: aaurelions/short-video-maker, rushindrasinha/youtube-shorts-pipeline, mutonby/openshorts, samuraigpt/ai-youtube-shorts-generator.

Sources: blog.lon.tv Sep 8 2026 V100 review; github.com/Comfy-Org/ComfyUI issue #15262; github.com/pytorch/pytorch issue #172351; github.com/NetVoobrazhenia/ComfyUI_Flash-Attention_v100; github.com/rwashy/H3-V100; github.com/deepbeepmeep/Wan2GP; ltxworkflow.com LTX 2.5 VRAM guide; huggingface.co/unsloth/LTX-2.3-GGUF; developers.tiktok.com Content Posting API.

## *** Sep 23 2026 — FULL RE-RESEARCH. 18/18 CLAIMS PASSED A BLIND VERIFICATION PASS (100%). THE VERDICT CHANGED. ***

Jack asked for the best video model on his setup, researched deeply. Every size below pulled live from the HF API and re-checked by an independent agent.

### *** THE PICK: Wan 2.2, NOT LTX. AND THE REASON IS EVIDENCE, NOT SPECS. ***

Wan 2.2 is the only video family with a PUBLISHED WORKING RUN ON A REAL TESLA V100 — github.com/pocketcoder-ch/v100-benchmarks-2026 marks Wan2.2 TI2V 5B "works (slow but runs)" on 2x V100 via sd.cpp, with no NaN workaround needed. Everything else on the list is inference from specs. Wan 2.2 is also the only family with 4-step distill LoRAs (lightx2v/Wan2.2-Distill-Loras, 2.60 GB, four files verified): ~20 steps down to 4, roughly 5x, the single biggest speed lever available on this box. Apache 2.0. *** CAVEAT THAT MUST BE CARRIED: those benchmarks ran on 32 GB V100s, not Jack's 16 GB cards. "It works" transfers; "it fits" does NOT. ***

### RANKED, WITH THE ARITHMETIC AGAINST 15.77 GiB PER CARD

| model | file | GB | GiB | fits ONE card? | audio? | license | | Wan2.2 TI2V-5B Q8_0 | unsloth | 5.40 | 5.03 | yes, huge margin | no | Apache 2.0 | | Wan2.2 T2V-A14B Q5_K_M x2 | QuantStack | 10.79 each | 10.05 each | yes (experts load one at a time by design) | no | Apache 2.0 | | Wan2.2 I2V-A14B Q5_K_M x2 | QuantStack | 10.79 each | 10.05 each | yes | no | Apache 2.0 | | HunyuanVideo 1.5 720p Q8_0 | jayn7 | 9.00 | 8.38 | yes | no | Tencent | | LTX-2.5-Distilled Q4_K_M | Abiray | 15.69 | 14.61 | yes, ~1.1 GiB spare — TIGHT | YES, native sync audio | LTX community | | LTX-2.5-Distilled Q3_K_M | Abiray | 12.92 | 12.03 | yes, comfortable | yes | LTX community | ENCODERS ARE THE REAL CONSTRAINT, not the transformers: LTX needs elix3r/gemma4-12b-with-proj-ltx-2.5-GGUF Q5_K_M 9,514,920,864 B (8.86 GiB) — 14.61 + 8.86 does NOT fit 15.77, so it must be loaded, run, then unloaded. Wan needs umt5_xxl_fp16 11,366,399,385 B. Hunyuan needs qwen_2.5_vl_7b at 16,584,415,576 B = 15.45 GiB, which alone nearly fills a card — the heaviest encoder burden of the three, and its fp8_scaled alternative is useless here. *** NEVER TAKE AN fp8 CHECKPOINT FOR THIS BOX. Volta has no FP8. *** A verifying agent suggested umt5_xxl_fp8_e4m3fn_scaled as "likely what you want on a 16 GB card" — that is exactly the wrong call on sm_70 and is recorded here so it is not repeated.

### *** LICENSE WORRY RESOLVED: LTX IS FINE FOR JACK. ***

LTX's own license page, verbatim: "If your company earns under $10M in annual revenue, you can self-host the full model weights, fine-tune, and use LTX commercially at no cost under the community license." Measured on total company revenue. So the Apache-2.0-vs-community distinction does not decide this for him; the V100 evidence does.

### *** THE LTX NaN SCARE IS ABOUT FLASH ATTENTION, NOT THE MODEL — AND IT REVERSES THIS FILE'S STEP 4 ***

github.com/ai-bond/flash-attention-v100 issue #36: LTX-2.3 on a Tesla V100-SXM2-16GB, CUDA 12.9.2, PyTorch 2.10, throws Input contains (near) NaN/+-Inf. The reporter's own conclusion: generation succeeds with flash attention DISABLED. So this file's "add ComfyUI_Flash-Attention_v100 and measure the delta" is now a known NaN source for LTX on Volta, not a free speed win. Try it last, and only with a NaN check on every render. (Note this is a different repo from the NetVoobrazhenia one recorded above; both exist.) It is also NOT evidence about LTX-2.5 — 2.3 and 2.5 are different models, and no public test of LTX-2.5 on sm_70 exists either way. That is a real unknown, not a solved problem.

### *** NEW AND IMPORTANT: A CONFIRMED VOLTA FP16 OVERFLOW BUG IN ggml/sd.cpp — ALL-BLACK OUTPUT ***

github.com/leejet/stable-diffusion.cpp issue #1292: all-black images on a Tesla V100 with Q4_0 quants, root-caused to FP16 tensor-core accumulation, fixed by adding GGML_CUDA_CC_VOLTA to the FP32-accumulate path in ggml-cuda.cu. Found on Z-Image Turbo but it is a general Volta GGUF-diffusion hazard, so it plausibly applies to Wan and LTX GGUFs too. PRACTICAL RULES IT IMPLIES: prefer F16 files over low-bit quants where they fit; keep the VAE in FP32 (the same repo's CogVideoX-5B run needed vae.to(torch.float32) on Volta); and check the first render for black frames before tuning anything.

### NOTHING BETTER EXISTS — CHECKED

Wan 2.5, 2.6 and 2.7 have NO open weights. The official Wan-AI HF org's newest repos are all Wan 2.2 generation (Wan2.2-Animate-2-14B Aug 2026, Wan-Dancer-14B Jul 2026); 2.5/2.6 shipped API-only and "Wan 2.7" is an SEO fabrication with no repo on any official channel. LTX-2.5 (released Aug 11 2026) is the newest LTX; no 2.6 or 3. Everything else open-weight — CogVideoX-5B (~24 GB), Mochi 1 (~20 GB), Open-Sora (24 GB+), SVD — is both lower quality and heavier. There is no model that is simultaneously better and smaller. MiniMax H3 stays ruled out (overflow + ~55 s/step).

### THE PLAN THAT FOLLOWS FROM ALL THIS

- Wan2.2 TI2V-5B Q8_0 first — the known-good V100 result, 5.03 GiB, leaves room for the encoder. Prove the pipeline renders a non-black clip before anything else.
- Add the 4-step LoRAs — biggest speed win, 2.6 GB.
- Then Wan2.2 I2V-A14B Q5_K_M for real quality on the posting pipeline.
- LTX-2.5 only if audio is wanted — it is the sole native-audio option, and the sole one with a real unknown on sm_70.
- Flash attention LAST, and treat a NaN as expected rather than surprising.

## *** Sep 23 2026 — "HOW FAST WOULD IT RUN". THE SPEED ANSWER, SEPARATING MEASURED FROM ESTIMATED. ***

Jack asked for generation speed on his box. Only two video numbers on real V100 hardware exist anywhere. Everything else here is scaled from other GPUs and is an ESTIMATE.

### MEASURED ON AN ACTUAL TESLA V100 (the only hard data)

| what | number | source | | LTX 2.5, 5-second 720p clip | ~3.5 minutes | Lon.TV Sep 8 2026, V100 32 GB | | MiniMax H3, 8-step 24,792-token workflow | 563.8 s cold / 490.8 s warm = ~55.4 s/step | rwashy/H3-V100, V100 16 GB | | Z-Image-Turbo, 1024x1024 image | ~64 s | pocketcoder-ch, V100 32 GB | | SDXL, 1024x1024 image | ~26 s | same | | Wan2.2 TI2V-5B | "works, slow but runs" — NO TIME PUBLISHED | pocketcoder-ch | *** The 32 GB and 16 GB V100s have the same compute; they differ only in memory size. So the LTX and Z-Image times transfer on speed, though not on what fits. ***

### THE NEAREST ANALOGUES FOR WAN, AND THE SCALING ARGUMENT

No Wan timing on Volta exists. Closest comparable setups (GGUF + encoder offload on a small card), from runaihome's community-gathered table:

- RTX 4070 12 GB, GGUF + T5 offload: 18-22 min per 5-second 480p clip.
- RTX 3090 at 640x480: ~7 s/frame, so ~9-10 min per 5-second clip; ~24 min at 720p.
- SaladCloud full-precision Wan 2.1 T2V-14B: H100 85 s at 480p / 284 s at 720p; A100 170 / 523; A40 501 / 1,083; RTX 4090 281 s at 480p and OOM at 720p; RTX 3090 OOM at 720p. Why the 4070 is the right anchor: V100-PCIE-16GB is ~112 TFLOPS FP16 tensor and 900 GB/s HBM2; the 4070 is ~116 TFLOPS and 504 GB/s. Compute is a wash and the V100 has nearly 2x the bandwidth. But the V100 has no Flash Attention 2, and attention is exactly where video's long token sequences cost the most. Those roughly cancel, so treat the V100 as 4070-class for video, give or take. NOTE THE SOURCES DISAGREE: Spheron quotes Wan 720p at 10-12 min on an H100 where SaladCloud measured 284 s on the same class of card. Community video timings vary by 2-3x on step count and resolution alone. Do not present any of these as precise.

### THE ESTIMATE, STATED AS AN ESTIMATE

| config | 5-second clip | basis | | LTX-2.5-Distilled, 720p | ~3.5 min | MEASURED | | Wan2.2 A14B + 4-step LoRAs, 480p | ~3-5 min | 4070 anchor / 5 for the step cut | | Wan2.2 TI2V-5B, 480p | ~5-9 min | 4070 anchor, scaled for 5B vs 14B | | Wan2.2 A14B, 480p, no LoRA (~20 steps) | ~15-25 min | 4070 anchor directly | | Wan2.2 A14B, 720p | 40-60 min | 3090's 480p-to-720p ratio applied | *** THE 4-STEP LoRAs ARE THE WHOLE BALLGAME FOR WAN: without them Wan is 4-6x slower than LTX; with them it is level. And they exist ONLY for the A14B models — there is no 4-step LoRA for TI2V-5B in lightx2v/Wan2.2-Distill-Loras. That partly undercuts TI2V-5B as the starting pick. ***

### WHAT THIS MEANS FOR THE POSTING PIPELINE, WHICH IS THE ACTUAL QUESTION

At 3.5-5 min/clip on ONE card, an 8-hour overnight run yields ~95-135 clips. Any realistic posting cadence needs a handful a day. Throughput is not the constraint; it never was. What is:

- Both V100s are currently committed to the production 27B (17.66 GiB across two 15.77 GiB cards). Video time is time the LLM is stopped, unless the freed-card re-layout happens.
- Encoder swapping. LTX's 8.86 GiB encoder cannot be co-resident with its 14.61 GiB transformer, so each batch pays a load/unload. Amortized over a batch sharing one prompt encode, negligible; per clip with a new prompt, 20-60 s from disk.
- It is a batch pipeline, not interactive. Nobody iterates on prompts at 4 min a look.

### HOW TO SETTLE IT, AND IT IS CHEAP

Render one 5-second 480p clip on each of the three families once the drive is home, and time it. That converts every estimate above into a measurement in about an hour of wall clock. Do it before building any scheduling around a number.

## *** Sep 23 2026 — "CAN I DO HIGHER QUALITY, RELATIVELY FAST?" YES, BUT NOT BY GENERATING AT HIGH RESOLUTION. ***

Jack asked whether higher-quality video is possible at all on this box and whether it can be fast.

### WHY BRUTE FORCE FAILS, AND IT IS NOT MAINLY VRAM

Diffusion-transformer attention is quadratic in latent tokens. 480p to 720p is 2.25x the pixels and therefore roughly 5x the attention cost; 1080p is ~4x the pixels of 480p and ~16x the attention. The V100 has no Flash Attention 2, so it pays that quadratic cost with the worst possible kernel. Separately, frame count multiplies tokens too, so clip length and resolution trade against each other in the same budget. Confirmation from the measured side: SaladCloud's full-precision Wan 2.1 T2V-14B run shows RTX 4090 24 GB doing 480p in 281 s and OOM-ing outright at 720p, and a 3090 OOM at 720p. Native high-res video is a big-VRAM game. *** SO: NATIVE 1080p IS OUT. Native 720p is reachable but slow. The answer is generate small, then upscale and restore — which is standard practice even on 80 GB cards, and mandatory here. ***

### THE UPSCALE / RESTORE STACK, ALL VERIFIED LIVE AND ALL FITTING ONE CARD

Downloaded by D:\models\pull_hq.py (~29 GB, ~15 min at 33 MB/s). | what | repo | bytes | role | | LTX-2.5 2x spatial upscaler IC-LoRA | Lightricks/LTX-2.5-22b-IC-LoRA-Pixel-Spatial-Upscaler | 327,322,640 | *** THE CHEAPEST QUALITY LEVER ANYWHERE ON THIS BOX. *** It is a LoRA that runs on the LTX-2.5 transformer already resident: no second model, no extra VRAM beyond 0.33 GB | | FlashVSR v1.1 | JunhaoZhuang/FlashVSR-v1.1 | 7,524,088,565 total | ONE-STEP diffusion SR with locality-constrained sparse attention. The speed pick for long clips. Ships its own Wan2.1 VAE | | SeedVR2 7B Q8_0 | cmeka/SeedVR2-GGUF | 8,835,170,080 (8.23 GiB) | ByteDance diffusion-transformer restorer, the QUALITY pick, strongest on degraded/AI-generated footage. _sharp variant same size. 3B Q8_0 is 3,660,613,984 as the fast fallback | LTX 2.5 also ships a documented TWO-STAGE HQ WORKFLOW — examples/ltx25-gguf-local-two-stage-hq.json inside elix3r/gemma4-12b-with-proj-ltx-2.5-GGUF, already on the download list. Low-res base pass, then a refine pass. Read it before hand-building anything. RIFE v4.26 frame interpolation is ~22 MB and ships with modern ComfyUI (models/frame_interpolation/). Nearly free, and doubles or triples effective fps, which reads as "smoother/better" for a fraction of the cost of generating more frames.

### VOLTA-SPECIFIC NOTES ON SeedVR2 (from the official ComfyUI node's own docs)

- The fp8 variants everyone recommends for 12-16 GB cards are useless here. GGUF is the Volta path, which is exactly why cmeka/SeedVR2-GGUF is on the list rather than the fp8 repack. The repo ships its own lcpp-seedvr.patch.
- Attention backend: PyTorch SDPA is the default and works. Flash Attention 2/3 and SageAttention are optional, and on this box FA is a known NaN source, so leave them off.
- BlockSwap and VAE tiling let it fit small cards by swapping transformer blocks GPU/CPU and tiling the decode.
- *** batch_size MUST follow 4n+1 (1, 5, 9, 13, ...) *** — the architecture processes a batch together for temporal coherence. A non-conforming value will fail or degrade.
- The CLI supports multi-GPU frame-level parallelism. Jack has two V100s, so upscaling is one of the few jobs here that can genuinely use both cards at once. This does NOT apply to generation, where a diffusion transformer cannot be split.
- The VAE encode/decode is often the bottleneck, not the upscaler. Larger batches help.
- torch.compile is claimed at 20-40% on the DiT. UNTESTED ON sm_70 and Triton support for pre-Ampere is doubtful — do not budget for it.

### THE PRACTICAL RECIPE, AND ITS HONEST COST

Generate 480p, then 2x upscale, giving roughly 960p output.

- generation: the 3-5 min per 5 s clip already recorded above (LTX distilled, or Wan A14B with the 4-step LoRAs)
- upscale: UNMEASURED on this hardware. No published V100 figure for SeedVR2 or FlashVSR exists. Expect it to add rather than multiply, and expect FlashVSR (one step) to be the cheap one and SeedVR2 (full diffusion) the expensive one.
- Total guess: high single digits of minutes per finished 5-second clip at ~960p. Still ~60-90 clips in an overnight run, far more than any posting cadence needs. THE HONEST BOTTOM LINE: quality is reachable, speed is acceptable for batch work, and the thing that is genuinely NOT available on this box is interactive high-res iteration. Treat it as an overnight render farm, not a creative tool you sit in front of.

## *** Sep 23 2026 — WHAT RESOLUTION IS ACTUALLY REACHABLE. AND A CORRECTION TO THE SPEED TABLE ABOVE. ***

Jack asked what resolution he could get to.

### NATIVE GENERATION CEILING: 720p. THAT IS A REAL CEILING, BUT 720p IS GENUINELY AVAILABLE.

| model | native resolutions | note | | Wan2.2 TI2V-5B | *** 720p @ 24fps, 5-second clips, NATIVE *** | vendor card: "supports both text-to-video and image-to-video generation at 720P resolution with 24fps" | | Wan2.2 T2V/I2V-A14B | 480p and 720p | 720p OOM'd a 24 GB RTX 4090 at full precision; GGUF + offload is what makes it reachable | | HunyuanVideo 1.5 | 480p and 720p GGUFs | plus latent upscalers targeting 720p and 1080p in Comfy-Org/HunyuanVideo_1.5_repackaged (85.8 MB and 201.4 MB) | | LTX-2.5 | designed up to 4K | not at 16 GiB; the distilled GGUF path is 720p-class here |

### *** VENDOR ANCHOR THAT CORRECTS THIS FILE'S EARLIER TI2V-5B ESTIMATE ***

Wan's own card: "generate a 5-second 720P video in under 9 minutes on a single consumer-grade GPU" (a 4090, and it states 24 GB minimum for that path). Scaling to a V100-PCIE-16GB: the 4090 is ~330 TFLOPS FP16 tensor and 1008 GB/s; the V100 is ~112 and 900, with no Flash Attention 2. So roughly 1/2 to 1/3 of a 4090 for this work. | | earlier estimate in this file | corrected | | TI2V-5B, 5 s, 720p | not stated | ~18-30 min | | TI2V-5B, 5 s, 480p | 5-9 min | ~8-13 min (2.25x fewer pixels) | The earlier 5-9 min line was optimistic. Use these.

### AFTER UPSCALING: THE MODELS ARE RESOLUTION-AGNOSTIC, SO THE CEILING IS VRAM AND TIME, NOT A MODEL CAP

Neither SeedVR2 nor FlashVSR publishes a maximum output resolution: you set a target and VAE tiling makes it fit, slowly. Practical chains:

- 480p native -> 4x (FlashVSR) -> ~1080p. Cheapest route to a deliverable file.
- 720p native -> 2x (LTX IC-LoRA or SeedVR2) -> 1440p. The quality route.
- 720p -> 4x -> 4K-class, possible, and pointless (below). *** 1080p FINISHED OUTPUT IS COMFORTABLY REACHABLE. 1440p is reachable. 4K is technically reachable and not worth it. ***

### *** THE POINT THAT MATTERS MORE THAN ANY OF THE ABOVE ***

Upscaling to 4K produces a 4K file, not 4K detail. The detail ceiling is whatever the base model generated; an upscaler invents plausible texture above that. So resolution past ~1080p buys file size, not quality. And the destination caps it anyway: short-form vertical is 1080x1920. For Jack's auto-posting use case, native 720p plus a 2x upscale already exceeds what the platforms deliver. Chasing 4K on this hardware is spending hours per clip on pixels nobody will ever see. THE RECOMMENDATION: target 1080x1920 vertical finished output. Generate at 480p or 720p, upscale 2x, stop there.

## *** Sep 23 2026 — "DOES THE UPSCALING TAKE RAM?" THE VRAM/RAM BUDGET FOR THE UPSCALE PASS. ***

Jack asked whether upscaling consumes memory. Answer: both, and only one of them is a constraint for him.

### VRAM IS THE REAL CONSTRAINT. THE BUDGET ON ONE 15.77 GiB CARD:

- SeedVR2 7B Q8_0 weights: 8.23 GiB resident, leaving ~7.5 GiB
- activations, which scale with FRAMES x RESOLUTION — this is the term that blows up. SeedVR2 processes a whole batch together for temporal coherence, so every frame in the batch is live in VRAM simultaneously
- VAE encode/decode, which the official node's docs say is often the bottleneck rather than the upscaler itself PUBLISHED VRAM TIERING (from the ComfyUI-SeedVR2 ecosystem docs): 8 GB or less -> GGUF + BlockSwap + VAE tiling, batch 1-5; 12-16 GB -> batch 5-13; 24 GB+ -> batch 13-45. *** SO JACK SITS IN THE 5-13 FRAME BAND, AND WITH THE 4n+1 RULE THAT MEANS BATCH 5, 9 OR 13. *** A 5-second 24 fps clip is 120 frames, so that is roughly 10-24 batches with overlap blending between them — which is a large part of why upscaling is slow here, and it is the first knob to tune. FlashVSR is far lighter: 7.52 GB total INCLUDING its own VAE, and it is ONE-STEP, so activation pressure is much lower. That is the reason it is the throughput pick for long clips.

### *** SYSTEM RAM IS A NON-ISSUE FOR HIM, AND THAT IS AN ADVANTAGE, NOT JUST AN ABSENCE OF A PROBLEM ***

BlockSwap works by moving transformer blocks between GPU and SYSTEM RAM. On a typical desktop that is itself a constraint. Jack has ~503 GiB, so for him BlockSwap costs only speed (PCIe transfers), never capacity. Decoded frame buffers are also trivial at his scale: a 5-second 1080p clip in fp16 is about 1.5 GB of system RAM; at 1440p roughly 2.6 GB. *** PRACTICAL RULE: turn BlockSwap and VAE tiling ON without hesitation, and treat BATCH SIZE as the one real VRAM dial. Start at 5, raise toward 13 while watching for OOM. ***

### HONEST GAP

Nobody publishes exact VRAM figures for SeedVR2 at a given batch size and output resolution, so the tier table is the best available guide rather than a measurement. One upscale run with nvidia-smi open settles it in five minutes — and pairs naturally with the thermal check in power-thermals-and-tuning, since both want a long run to watch.
