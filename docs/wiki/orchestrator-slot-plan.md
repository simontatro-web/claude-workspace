# orchestrator-slot-plan

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 23, 2026).
> Cowork-only links kept as page names.
>
> Summary: The Sep 22 2026 slot-by-slot model plan for the jarvis-1 orchestrator — the GPU re-layout that frees a whole V100, the uncensored/coding/router/big-model picks with verified GGUF sizes, and the ordered build sequence. Read before assigning any model to an orchestrator slot.

Answers Jack's Sep 22 2026 question: which models for the orchestrator, including a fast-but-capable model, an uncensored model, a coding model, a safe small orchestrator, and local video. His stated constraints that pass: video must be LOCAL ONLY on jarvis-1; storage plan is 990 PRO plus a 4TB drive not yet purchased (he asked for other hardware storage options); he wants the GPU layout re-planned, not just accepted; priorities are speed-testing the giants, a working coding agent, autonomous video posting, a safe background orchestrator, and generally "test different systems out and maximize capability." Supersedes the slot inventory in jarvis-model-research (Sep 13 2026), which predates 503 GiB RAM, the b11089 rebuild, and Qwen3.8-Flash-Next. Live build status stays in jarvis-orchestrator.

## *** THE GPU RE-LAYOUT: -sm layer IS PIPELINE-PARALLEL, SO THE SECOND CARD BUYS CAPACITY, NOT SPEED ***

This is the insight that unlocks everything else, and it follows from facts already in memory rather than new research.

- local-model-landscape: -sm layer is the ONLY working split mode on V100 (-sm tensor asserts/hangs per llama.cpp issue #27366; -sm row is CUDA-unavailable). Layer split is PIPELINE parallel — you get roughly ONE card's bandwidth, not the sum. That issue's own numbers: pp4096 777.09 split vs 774.81 single-GPU.
- Therefore: a 27B that FITS ON ONE CARD gives up almost nothing in throughput, and hands back a whole free 16 GiB V100. The current layout (Q4_K_M 17.66 GiB spread over both cards, GPU0 15,078 / GPU1 10,266 MiB) is spending a second GPU purely to hold weights.
- The KV cache is nearly free on this model: local-model-landscape measured the 27B as HYBRID — 3 recurrent layers then 1 full-attention, repeating, so only 16 of 64 layers hold a growing KV cache. q8_0 KV at 8192 ctx = ~272 MiB; at 32K ctx ~1.1 GiB.
- DROP THE VISION TOWER on the GPU slots. The 4.8 GiB card imbalance measured Sep 21 is the CLIP graph materializing a full 4.27 GiB attention matrix because FA is compiled out. No mmproj = no 4.27 GiB workspace = the real reason a single card becomes viable.

### PROPOSED LAYOUT (not yet built or measured)

| Card | Model | File size | Why | | GPU0 | Qwen3.8-27B MTP quant, Q3_K_M ~13.5 GB / 12.57 GiB (Jackrong/Qwen3.8-27B-MTP-GGUF) | 12.57 GiB + ~1.1 KV @32K + ~1 compute ≈ 14.7 GiB of 16 | the judge/interactive slot, now with a native MTP draft head | | GPU1 | Uncensored 27B, RentedNoodle GSQ-RCO-IQ3_XXS-Uncensored-MTP 10,442,827,584 B / 9.72 GiB | ≈ 10.8 GiB used, ~5.2 GiB spare | second permanently-resident GPU model, which does not exist today | THE TRADE: Q4_K_M -> Q3_K_M is a real quality loss on the judge. What buys it back is MTP. local-model-landscape has the anchor: 2x V100-SXM2-16GB running Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp measured decode 47.3 t/s (kvmem issue #24) versus Jack's measured 28.09 t/s at Q4_K_M layer-split. So the smaller+MTP configuration is plausibly FASTER than what he runs now, on one card instead of two. MEASURE BEFORE COMMITTING: run the Q3_K_M+MTP single-card config on port 8081 with the safe foreground harness already documented in local-model-landscape (stop the service, timeout 60 llama-server ... --port 8081, restart), and A/B decode t/s and a few answer-quality prompts against the live Q4_K_M. If quality drops too far, the fallback is: judge keeps both cards, uncensored and video become on-demand swaps. CONFLICT TO RESOLVE: video generation also wants a whole card (see video-generation-v100). Video is a SCHEDULED BATCH job, so the supervisor should stop the GPU1 model for the render window and restart it after. That is exactly the ensure_slot swapping logic already designed in jarvis-model-research, which was previously unusable because no card was ever free.

## SLOT-BY-SLOT PICKS

### 1. BIG / "fast but still capable" — Qwen3.8-Flash-Next UD-Q4_K_XL. This is the biggest single win available.

111,334,654,784 B = 103.7 GiB. 6B active params. llama.cpp support MERGED Aug 27 2026 (PR #27742) — runs on stock, no fork. AA Intelligence Index v4.3.2 40 vs the 27B's 34 and GLM-5.3 full's 45. Estimated 9-15 t/s baseline on Jack's box and ~18-27 t/s with NUMA mirroring plus its published MTP draft GGUF, against GLM-5.3 full's 1.6-2.7 t/s. Fits inside ONE socket, so no QPI tax AND mirrorable at full quality — the only big model on file that is both. Full detail, sizes, risks and third-party measurements in qwen38-flash-next. This changes the recommendation order for the "speed test the giants" goal: test Flash-Next FIRST, because it is the one that could actually be used all day rather than admired once.

### 2. THE GIANTS, for the speed-test bench — keep GLM-5.3, add Hy4, skip Flash

Unchanged from local-model-landscape and cpu-moe-speed-levers, restated as a plan:

- GLM-5.3 (full) — runs on stock today (glm-dsa), AA 45, ~1.6-2.7 t/s. The capability ceiling he can actually load. Keep.
- Hy4-preview UD-IQ1_M 235.4 GB / 219.2 GiB — arch merged, now fits with room. Worth ONE benchmark run for comparison, but 49B active makes it the slowest of the set and its STQ1_0 quant is still blocked on the unmerged ternary AVX2 kernel.
- GLM-5.3-Flash — do NOT chase near-term. All three mainline PRs open, #27773 described as unmaintained, the reference build is a community patch stack on an abandoned PR. The one bright spot is ik_llama.cpp PR #2376, which has real working user reports — revisit only if he wants to build that fork.
- MiMo-V2.6-Pro — still no Pro-scale GGUF, and ~498 GiB of weights against 503 GiB RAM means mmap paging, not residency. Watch for a community GGUF; do not plan around it.
- Corrected benchlm.ai coding-leaderboard numbers (verified Sep 22): Hy4-preview 64.2 (highest-ranked open weight, 14th overall), GLM-5.3 61.4 (19th). Earlier notes said 64.0 / 62.0 — wrong, do not reuse.

### 3. UNCENSORED — verified repos, with exact files

The blind check caught that an earlier draft invented two huihui filenames. These are the VERIFIED contents:

- huihui-ai/Huihui-Qwen3.8-27B-abliterated-GGUF (2,382,379 downloads, modified Sep 21 2026, base Qwen/Qwen3.8-27B). Contains ONLY Q2_K 10,864,592,160 / Q3_K 13,500,736,800 / Q4_K 16,810,714,400 / Q5_K / Q6_K / Q8_0 plus _L variants, bf16 54,657,733,920, and mmproj-model-bf16 931,145,888. NO IQ quants and NO MTP file — do not look for them. Method described by the author as "a crude, proof-of-concept implementation to remove refusals," abliterating layers ~17-52 while preserving vision.
- Blackfrost-AI/Qwen3.8-27B-ABLITERATED-GGUF — Q3_K_S 12,073,955,520, Q3_K_M 13,301,444,800, Q4_K_M 16,547,401,920, plus separate MTP draft GGUFs (mtp-...-Q4_0 2,008,056,032, Q8_0 3,164,008,672) and mmproj Q8_0 629,247,488. Q3_K_S + mtp-Q4_0 = 14.08 GB total, comfortable on one card.
- RentedNoodle/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-Uncensored — the pick. ...-MTP.gguf 10,442,827,584 B (MTP inside the file, not a separate draft), v1.1 10,466,420,544 B, imatrix.dat, mmproj Q8_0 629,247,648, a froggeric tool-use jinja template, and a real evals/ directory with coherence / livebench / needle / toolcall prompt sets and raw logs. Smallest, has MTP, ships its own evals, and GSQ-RCO is the same quant family as the file measured at 47.3 t/s on 2x V100. NOTE ON THE FORMAT: GSQ-RCO = Gumbel-Softmax Quantization plus Riemannian Constrained Optimization, per-tensor bit allocation under a size budget. ISTA-DASLab (the originators) claim their IQ3_XXS holds 99.4% of base task average at 4.7x smaller — [VENDOR], and that figure is for Flash-Next, not for this abliterated 27B.

### 4. CODING — Flash-Next wins outright. Qwen3-Coder-Next's headline number was a benchmark-variant trap.

*** CORRECTION Sep 22 2026, from Jack's question "is Qwen3-Coder-Next better at coding than the bigger models?" *** The "SWE-Bench Verified 70.6" figure carried in this file and in jarvis-model-research is SWE-bench VERIFIED, which is not comparable to the SWE-bench PRO numbers quoted for every other model here. Qwen's own model card reports BOTH: | Qwen3-Coder-Next, from Qwen's card | score | | SWE-bench Verified | 70.6 | | SWE-bench Pro | 44.3 | | Terminal Bench 2.0 | 36.2 | THE RULE TO CARRY: never compare a Verified score to a Pro score. CORRECTED Sep 22 2026 by a verification pass — an earlier version of this note said the gap was "~20-25 points" citing digitortoise.com. That was wrong and understated it. Scale's own launch framing: "While most top models score over 70% on the verified version, the best-performing models, OpenAI GPT-5 and Claude Opus 4.1, score only 23.3% and 23.1% respectively on SWE-Bench Pro" — a ~47 point drop. BEST ANCHOR, one model one card: Qwen3-Coder-Next reports Verified 70.6 AND Pro 44.3, a 26.3 point drop. The gap narrows as models improve (Pro's top has climbed from ~23% to 61.5%), so do NOT apply a fixed offset; if only a Verified score exists, treat the model as UNRANKED on coding. OpenAI retired SWE-bench Verified on 2026-02-23 (openai.com/index/why-we-no-longer-evaluate-swe-bench-verified). Their audit: 59.4% of sampled problems had flawed test cases (35.5% overly strict, 18.8% testing undocumented behaviour), and every frontier model tested could reproduce the original human-written fix, i.e. contamination. They now recommend Pro. So Coder-Next's headline is on a deprecated, contamination-compromised benchmark. *** NEUTRAL SCORE NOW EXISTS FOR Qwen3-Coder-Next, AND IT IS BRUTAL: Artificial Analysis Intelligence Index v4.3.2 = 9. *** (An earlier note here wrongly said AA has no page for it; artificialanalysis.ai/models/qwen3-coder-next exists.) Against Flash-Next's 40 and a board ceiling of 53. READ IT WITH CARE: the AA index is reasoning- and agent-heavy and this model is non-thinking-mode-only by design, which tanks it — a 9 means "not a reasoning model", not "cannot write code". It does settle that it is unusable as a general-purpose slot. AA also gives it 79.7B total / 3B active, 110.9 t/s output, Apache 2.0, released Feb 2026. HEAD TO HEAD ON SWE-BENCH PRO, the comparable axis: | Model | SWE-bench Pro | | Qwen3.8-Flash-Next | 62.5 | | Atria Dawn Preview | 59.6 | | Qwen3-Coder-Next | 44.3 | Flash-Next beats the dedicated coder by +18.2 points. benchlm's composite (SWE-bench Pro 50% + LiveCodeBench 50%) agrees on the tier: Hy4-preview 63.8 highest open weight, GLM-5.3 60.9, GLM-5.2 60.6, Qwen3.8 Max 60.3. Neither Qwen3-Coder-Next nor Flash-Next is listed there. NOTE ON benchlm DRIFT: it is a live leaderboard. Two fetches the same day gave Hy4 64.2 then 63.8, and GLM-5.3 61.4 then 60.9. Treat its numbers as +/- ~0.5 and never quote them to one decimal as though fixed. (An earlier line in this file recorded 64.2 / 61.4 as "corrected" — both readings are within drift; the tier ordering is what is stable.) CONCLUSION: the coding slot is Qwen3.8-Flash-Next, not a dedicated coder. Same model as slot 1, zero extra download, zero extra RAM. Qwen3-Coder-Next still has ONE real argument: size and speed. 80B total / 3B active (half Flash-Next's 6B), 48 layers, 512 experts with 10 active, 262,144 context, non-thinking mode only. Sizes verified from unsloth/Qwen3-Coder-Next-GGUF: UD-Q2_K_XL 26,760,515,584 / UD-IQ3_XXS 28,482,506,752 / UD-Q3_K_XL 36,282,685,440 / UD-Q4_K_XL 49,608,478,720. At ~1.5 GB/token it is plausibly ~2x Flash-Next's decode speed in a third of the RAM (33.8 GiB vs 103.7 GiB). So it is the right pick ONLY if the requirement is a small always-resident coder running beside everything else, or if Flash-Next's RAM is needed elsewhere. On capability it loses badly.

- THE SHARED GATE for both: Gated DeltaNet. llama.cpp issue #22967 is an open RFC — large prompt processing still uses the token-sequential CUDA kernel, and the chunked CUDA prefill (PR #26001) is NOT merged. The chunked algorithm already exists in the CPU reference path, so run these CPU-heavy and do not expect the V100s to fix prefill.
- The existing GVS5H harness around the 27B (agent-harnesses) remains the fallback and is already proven; a dedicated coding model is an upgrade to it, not a replacement for it.

### 5. ROUTER / "small orchestrator that can't hurt the system"

The safety answer is architectural, not a model choice: the router must have NO tool access and NO shell. It emits a label, nothing else. jarvis-orchestrator already establishes that run_host_command is an unrestricted shell with no allowlist and that Jack declined a tool-level denylist — so the guardrail has to be that the background model simply never holds that tool.

- Model: ggml-org/Qwen3-1.7B-GGUF Q4_K_M, 1,282,439,264 B, CPU-only (-ngl 0, CUDA_VISIBLE_DEVICES=""). Published by the llama.cpp maintainers, so sm_70 risk is nil, and CPU cost per classification is well under a second.
- Force the output with --json-schema / GBNF. Mechanically valid output means the router's JSON reliability is not a selection criterion — it only has to pick the right label.
- Alternative kept for A/B: empero-ai/Qwen3.8-2B-Distill-GGUF Q4_K_M 1,312,164,224 B, same qwen35 arch/chat template as the judge.

### 6. THE "JEV" QUESTION, ANSWERED [VERIFIED]

Jack asked about "jev and stuff." Jev is TypeSafe AI's "System One" / decision model — proprietary and API-only. It takes text and returns calibrated floating-point probabilities instead of text: Bernoulli yes/no, multiple-choice, and numeric ratings. $0.042/M input, output free. Simon Willison covered it Sep 21 2026; TechCrunch Sep 18.

- Open alternative jaredpalmer/kev: a LoRA adapter plus a readout head on Qwen2.5-0.5B (the repo's social line says Qwen3.5, the README and model card say Qwen2.5 — the README is correct). 38 MB, ~160 ms for a six-question request, overall accuracy 0.799, ECE 0.065 on 1,350 held-out questions. No GGUF, no llama.cpp path, CUDA untested (Apple MPS only). NOT production-ready for jarvis-1.
- BUT THE IDEA IS THE RIGHT ONE AND IS FREE TODAY. The reason to care is that Jack's router slot is a classification problem, not a generation problem, and llama.cpp can already do the Jev-shaped thing: constrain generation to a fixed label set with a GBNF grammar and read the token logprobs as a calibrated confidence. That gives a probability per route with no new model, no new runtime, and no hallucination surface. Build the router that way.
- Also checked and ruled out: Sakana AI's Fugu Max / Fugu Ultra v2 (Sep 11 2026) are API-only orchestration systems — they route to the leanest capable model, which validates Jack's whole architecture, but they are not open weights and cannot be run here.

### 7. VIDEO — see video-generation-v100

Short version: it works on Volta, LTX 2.5 measured ~3.5 min for a 5s 720p clip on a V100, you MUST use the PyTorch cu126 wheel (2.11 drops sm_70 from cu128+), and FP16 overflow is a real per-model trap. Start with LTX 2.3 GGUF at Q3/Q4 on one card.

## STORAGE — HE HAS NOT BOUGHT THE 4TB YET, AND HE MAY NOT NEED IT AS URGENTLY

Re-running the math from model-storage-plan with Flash-Next in the picture:

- Qwen3.8-Flash-Next UD-Q4_K_XL is only 111.3 GB. GLM-5.3 UD-Q4_K_XL is 467.3 GB. 990 PRO is 915 GiB with ~53 GiB spent on OS/toolchain ≈ 862 GiB usable.
- Flash-Next (104 GiB) + GLM-5.3 at UD-Q2_K_XL (236 GiB) + a coding model (34 GiB) + the two 27B GPU quants (~22 GiB) ≈ 396 GiB — all of it on the 990 PRO with room to spare. The HDD only becomes necessary for GLM-5.3 at Q4_K_XL (435 GiB) or Hy4 (219 GiB) on top.
- The residency rule from model-storage-plan still governs: models that FIT in RAM are load-once, so cheap bulk storage is fine for them; only a model that must page needs NVMe.
- Buy options, cheapest-risk first: (a) do nothing yet, because Flash-Next removes the urgency; (b) the already-priced Seagate SkyHawk 4TB CMR $169.99 SKU 066910 + Vantec NexStar HX USB 3.0 enclosure $34.99 SKU 094532 = $204.98 (~$47/TB), USB 3.0 confirmed present on the box; (c) recertified enterprise SATA from ServerPartDeals / GoHardDrive — historically 12-14TB HGST Ultrastar / WD Ultrastar units at roughly $73-135 each with multi-year warranties, i.e. ~$6-11/TB, four to seven times cheaper per TB than Micro Center. PRICES NOT VERIFIED THIS PASS — serverpartdeals.com blocks automated fetching (robots.txt) and Claude-in-Chrome was unreachable, so these are historical deal-thread figures and must be checked live before buying; (d) a second M.2 NVMe on the $14.99 Micro Connectors PCIe 3.0 x4 adapter (SKU 099994), which is the zero-unknown route since it needs no caddy, backplane or SATA power.
- Still true: DO NOT buy the DRAM-less TeamGroup G50, and do not buy a Seagate BarraCuda 4TB (SMR).

## BUILD ORDER (recommended, not yet agreed with Jack)

- grep -ril "qwen4exp\|glm-dsa\|hy_v4" ~/llama.cpp/src/ on b11089 — free, settles what the binary already supports.
- Download Qwen3.8-Flash-Next UD-Q4_K_XL (111 GB) and its MTP draft GGUF. Measure decode and prefill. This is the highest-value single action available.
- Test prompt caching on it with -lv 4 and look for "forcing full prompt re-processing" — Gated DeltaNet is the high-risk architecture class for this, and a break here would eat the speed win on agentic use.
- Single-card 27B A/B on port 8081 (Q3_K_M+MTP vs current Q4_K_M) to prove the GPU re-layout.
- Load the uncensored GSQ-RCO IQ3_XXS-MTP on the freed card.
- Router on CPU with a GBNF label grammar and NO shell tool.
- ComfyUI + cu126 + LTX 2.3 GGUF on one card; wire renders in as a job type.
- Only then benchmark GLM-5.3 full and Hy4 as the slow-capability bench.

## *** Sep 24 2026 — SLOT AUDIT AGAINST THE FAST-HOUSE DOWNLOAD. ONE HARD BLOCKER FOUND, PLUS FOUR SLOTS THAT WERE NEVER SPEC'D. D:\models\pull_orch.py. ***

Jack Sep 24 2026, at the fast house: "I want to fully build the model orchestrator system. Do we have the small antihallucination model? what about the website verification model? ensure we have all these models, even if they're tiny."

### *** THE BLOCKER: THE JUDGE-SLOT MTP QUANT WAS NEVER DOWNLOADED, AND IT IS WHAT THE WHOLE RE-LAYOUT RESTS ON. ***

This file's build order step 4 is the single-card 27B A/B, and steps 5 and 7 (uncensored on the freed card, video on a card) DEPEND on it. The file was listed as item #4 of the amended manifest in model-download-manifest and then never entered pull.py's ITEMS. Verified live off the HF tree Sep 24: Jackrong/Qwen3.8-27B-MTP-GGUF → Q3_K_M 13,500,736,832 B (12.57 GiB) and Q4_K_M 16,810,714,432 B (also IQ4_XS 15,420,450,112, Q2_K 10,864,592,192, BF16 54,657,733,952, and mmproj-F32.gguf 1,842,940,128 — F32 is the ONLY mmproj this repo ships). QUEUED BOTH Q3_K_M AND Q4_K_M, because they answer different questions and one variable each: Q4_K_M-MTP against the live non-MTP Q4_K_M isolates "does the MTP head help"; Q3_K_M-MTP answers "does it fit one card" (12.57 + ~1.1 KV at 32K + ~1 compute ≈ 14.7 of 16 GiB). 30.3 GB for both.

### *** THE ANTI-HALLUCINATION MODEL HE ASKED FOR: vectara/hallucination_evaluation_model (HHEM-2.1-Open), 438,535,352 B, 157k downloads. ***

It is a CROSS-ENCODER, not a chat model, and that is exactly why it belongs here. Input is (source passage, generated claim); output is a factual-consistency probability. It has no opinions and cannot be talked out of its answer, which is the property a generative judge lacks — the same distinction this memory already draws between tests that run and models that opine. Runs on CPU in milliseconds. Ships custom modeling code (modeling_hhem_v2.py, configuration_hhem_v2.py), so it needs transformers with trust_remote_code, NOT llama.cpp. Use it as the mechanical gate on every RAG answer and every research finding before a big model sees it. Second, complementary: RichardErkhov/grounded-ai_-_phi3.5-hallucination-judge-merge-gguf (~2-3 GB GGUF) for when a natural-language EXPLANATION of the unsupported claim is wanted. Primary gate = the cross-encoder; the generative judge is the second opinion, never the gate.

### *** THE WEBSITE VERIFICATION MODEL: unsloth/Qwen3-VL-4B-Instruct-GGUF UD-Q4_K_XL 2,546,342,176 B + mmproj-F16.gguf 836,180,640 B ≈ 3.4 GB. ***

Qwen3-VL-32B (20 GB, queued separately) is for when reading a diagram MATTERS. This is the one that belongs in a REVIEW LOOP that fires after every build, where a 20 GB model is the wrong tool. Full quant table captured: UD-IQ1_M 1,143,485,216 through Q8_0 4,280,406,816; BF16 8,051,286,560; mmproj BF16 839,326,368 / F16 836,180,640 / F32 1,661,409,952. *** THE FRAMING THAT MATTERS AND MUST NOT BE LOST: in the website-review loop the MODEL IS THE LAST AND WEAKEST LINK. The console errors and the DOM assertions are ground truth; the VLM only judges what a human would see. Never let the model's opinion override a console error. ***

### TWO MORE SLOTS THAT WERE NEVER SPEC'D, AND BOTH ARE FILTERS RATHER THAN ADVISORS

- protectai/deberta-v3-base-prompt-injection-v2, ~740 MB, 842,724 downloads — the standard classifier. Two placements: every page the browser agent reads, BEFORE that text reaches a model holding tools; and every stranger's message on a public endpoint. A classifier sits IN the data path; a prompt instruction only asks a model to behave, which this box's own incident log says is not enough.
- mradermacher/Qwen3Guard-Gen-4B-GGUF, ~2.5 GB — Qwen's safety classifier in GGUF, so llama-server hosts it. This is the gate for WANT 7's public-facing preset, on its own port with no tools and no memory. Family: Gen 0.6B (157k dl) / 4B (270k) / 8B (50k), plus Stream variants; GGUFs exist for all three Gen sizes.

### ROUTER — the named pick was also never downloaded

ggml-org/Qwen3-1.7B-GGUF Q4_K_M, 1,282,439,264 B, plus the A/B alternative empero-ai/Qwen3.8-2B-Distill-GGUF Q4_K_M ~1,312,164,224 B. Both queued. The architectural rule stands unchanged: CPU-only, --json-schema/GBNF-forced labels, logprobs as calibrated confidence, and NO tools and NO shell, because the guardrail cannot be behavioural.

### CHECKED AND DELIBERATELY NOT QUEUED

A dedicated UI-grounding model (UI-TARS / OS-Atlas / ShowUI class) that returns element coordinates. Qwen3-VL already grounds, the DOM is reachable through the existing CDP bridge and is EXACT where a coordinate prediction is a guess, and none of that family has a settled llama.cpp path. Revisit only if DOM assertions prove insufficient. TOTAL for pull_orch.py: ~55 GB, and 30 of it is the judge quant that unblocks the re-layout.
