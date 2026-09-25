# model-benchmark-dataset

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 23, 2026).
> Cowork-only links kept as page names.
>
> Summary: The cross-compared model benchmark dataset built for Jack Sep 22 2026 (models.json + model-benchmarks.md) — what is in it, the source-tagging scheme, the neutral AA v4.3.2 rankings, and the benchmark traps it encodes. Read before quoting any model benchmark number or building routing logic.

Built Sep 22 2026 because Jack asked for "all the relevant AI models, cross compared so none of the scores are misconstrued by vendor reported results," to hand to Jarvis to save and use for task routing. Scope he set: open weights, plus Claude Opus on the same tests as a yardstick; vendor numbers included but clearly tagged. Related: orchestrator-slot-plan, qwen38-flash-next, atria-dawn-preview, local-model-landscape.

## DELIVERED FILES

v1.2 — models.json (72 KB, 28 models, 207 tagged scores, 8 traps, routing table + dated watch list) and model-benchmarks.md (human summary). JSON is the one Jarvis parses.

## *** SECOND PASS Sep 22 2026 — THE BIGGEST FIND: MiMo-V2.6-Flash, WHICH v1.1 OMITTED ENTIRELY ***

Jack said "do more searching" and this is what it turned up. A real omission, not a rounding error. ggml-org/MiMo-V2.6-Flash-RL-GGUF — PUBLISHED BY ggml-org THEMSELVES (the llama.cpp maintainers, via github.com/ggml-org/convert). Architecture support is therefore GUARANTEED, not inferred from a merged PR. That is a stronger guarantee than any other big model on file has.

- 309B total / 15B active, MIT, 1M context, 48 layers, 256 routed experts with 8 active, 128-token sliding window, native omnimodal (text, image, video, audio).
- SIZES [VERIFIED from the HF tree API]: MXFP4 167,369,465,120 B = 167.4 GB = 155.9 GiB; Q2_K 125,717,568,800 B = 117.1 GiB; mtp sidecars MXFP4 and Q8_0 both 2,383,728,832 B; mmproj Q8_0 1,564,438,112 B covering BOTH vision and audio encoders.
- Launch line straight from the repo: llama serve -hf ggml-org/MiMo-V2.6-Flash-RL-GGUF:MXFP4, with --mtp for the speculative sidecar.
- FITS ONE SOCKET at MXFP4 (155.9 GiB of ~251) — no QPI tax, and NUMA-mirrorable (2 x 156 = 312 GiB of 503). Same structural advantage as qwen38-flash-next.
- SPEED ESTIMATE: 15B active x 4.19 bpw = ~7.9 GB/token → ~5 t/s at ~39 GB/s, plausibly 8-12 with mirror + MTP. MXFP4 on Volta is already VERIFIED working via the DP4A path (see mimo-v2.6-feasibility).
- THE CATCH: no Artificial Analysis page (404), so NO neutral capability score at all. Its sibling MiMo-V2.6-Pro scores 46 but that is a 1.02T/42B model and the number does NOT transfer. Vendor only: DeepSWE v1.1 67.9 (Pro 71.9), Toolathlon-Verified 73.6 (Pro 76.9), CyberGym 95.1 (Flash BEATS Pro's 94.0, odd enough to distrust).
- Documentation conflict to check before trusting speculative decoding: the card documents a FIVE-layer MTP drafter while config specifies THREE. RECOMMENDATION GIVEN: download BOTH this and Qwen3.8-Flash-Next and A/B them. One has the neutral score (Flash-Next, 40), the other has zero architecture risk. Neither dominates.

## *** DATED WATCH LIST (new in v1.2) ***

- Step 5 Preview (StepFun) — AA 44, and this is the best watch item on the list. 600B total / 27B active, 92-layer narrow-deep sparse MoE, 1M ctx, text+image+video in. One index point below GLM-5.3's 45 at 27B active instead of 40B, so roughly 2.3 t/s vs GLM's 1.6 for near-identical neutral capability. At Q4 ~372 GB / ~346 GiB. UNRESOLVED CONFLICT, do not treat as settled: Artificial Analysis states "Step 5 Preview is proprietary. The model weights are not publicly available." Two independent outlets (pandaily, marktechpost) state "Open weights land on October 15, 2026." Both can be true if AA has not updated. CHECK ON OR AFTER 2026-10-15. PROVENANCE WARNING: TypeSafeAI/Step-5-Preview-BF16 already exists on HF — 1.21 TB usedStorage, 604.3 GB BF16, 87 downloads, modified Sep 20 2026, NOT gated. TypeSafeAI is the Jev company, not StepFun. A third party hosting 604 GB of an officially unreleased model is unexplained. DO NOT DOWNLOAD without establishing provenance. Vendor scores: FrontierFinance 66.4, DRACO 83.3, DeepSWE v1.1 67.7, StepCodeBench 49.0 (their own eponymous benchmark), ProgramBench 80.5. Output 92.8 t/s, TTFT 4.25 s.
- Muse Spark 1.3 (Meta) — AA v4.3.2 = 48, which would be the highest-scoring open weight in existence (above MiMo-Pro's 46 and GLM-5.3's 45). Zuckerberg said an open-weights flagship is coming "soon"; Meta said Aug 10 that Muse Spark 1.2's weights would open "in the coming weeks" and no repo had appeared by early September. No version, license or param count committed publicly. Muse Glimmer 30B (Apache 2.0, already out) is the distilled sibling and scores only 19 — the distillation gap is enormous, so Glimmer is no guide to Spark.
- MiMo-V2.6-Pro (46) — waiting on a Pro-scale GGUF. 4. DeepSeek V4.1 Flash (39, 16B active) — no runtime anywhere. 5. MiniMax-M3 (29, only 128 GB) — three unmerged PRs.

## *** TWO NEW TRAPS FOUND IN THE SECOND PASS ***

stale_neutral_leaderboards (CRITICAL). Artificial Analysis is effectively the ONLY neutral source tracking 2026-current models. Verified this pass:

- LiveBench: top is o3-mini 0.846, GPT-5.5, GPT-5.4. Best open model Qwen3-235B-A22B 0.771. No GLM-5.3, no Qwen3.8, no MiMo, no Hy4.
- Aider Polyglot: top is GPT-5 0.880, DeepSeek-V3.2-Exp 0.745. Newest open entry Qwen3-Next-80B-A3B 0.498. No Claude, GLM, MiMo or Hy4 entries at all.
- Scale SWE-bench Pro: newest open models are qwen3-coder-480b-a35b, deepseek-v3p2, glm-4.6. CONSEQUENCE: for Hy4-preview, Atria Dawn, MiMo-V2.6-Flash and Qwen3-Coder-Next there is NO neutral automated score anywhere. aa_article_vs_index_version (HIGH). AA's own ARTICLES quote older index versions than its model pages. Its "Sub-32B Open Weights" article lists Gemma 4 31B (Reasoning) at 39 and Qwen3.5 27B at 42; the current v4.3.2 model page gives Gemma 4 31B (Reasoning) 19. Same organisation, same model, 20 points apart. Likewise the widely-quoted "Muse Spark 1.2 = 54" is an older version and sits ABOVE the current v4.3.2 ceiling of 53.

## OTHER v1.2 ADDITIONS

- GLM-5.2 (max) = 34 on v4.3.2, full breakdown: Briefcase 1233, GDPval 1358, AutomationBench 28%, Terminal-Bench 4.0 just 1% (vs GLM-5.3's 42%), SciCode 51, HLE 41, GDP.pdf 10, CritPt 21 (the ONLY eval where 5.2 beats 5.3's 19), Omniscience 4, LCR 78, 68 t/s. The 5.2 -> 5.3 jump was real and large: +11 index points and Terminal-Bench 1% -> 42%. RELEVANT TO atria-dawn-preview, which is post-trained from the 5.2 base, not 5.3.
- Nothing GPU-sized beats Jack's resident 27B. On v4.3.2: Qwen3.6-35B-A3B (Reasoning) 18, Gemma 4 31B (Reasoning) 19 (AA marks it estimated), versus Qwen3.8-27B (xhigh) 34. Gemma 4 31B also posts AA-Omniscience −48, the worst in the dataset.
- Hy4-preview finally has ONE non-vendor signal: WebDev Arena, a BLIND HUMAN-PREFERENCE arena (two anonymised models build the same prompt, humans vote). Reported ~5th overall and ~3rd among open source on launch day, in a tier with Claude Opus 5 Max, Kimi K3 Max, Qwen3.8-Max, Claude Opus 5 High and GLM-5.3-Flash. BUT it is a vendor-cited snapshot of a continuously re-ranking board. A second independent source confirms Hy4 has no independent scores anywhere: no public automated leaderboard, no third-party eval lab, no AA page.

## *** PROCESS NOTE WORTH KEEPING: THE FIRST DRAFT FAILED AT 65.4% ***

A blind adversarial agent checked 26 claims and found NINE wrong. Jack's 95% bar caught a draft that looked authoritative and was not. The failure modes, all worth watching for again:

- A FABRICATED MODEL ENTRY. A WebFetch summary of an AA comparison page returned "Claude Opus 5.5 = 58" with a complete ten-eval breakdown. Claude Opus 5.5 is not on the Artificial Analysis index at all. The whole row was invented downstream of a bad page summary. LESSON: a single-page fetch that returns a suspiciously complete table is not corroboration; cross-check any headline number against the leaderboard listing.
- An invented discrepancy ("DeepSeek V4.1 Flash reads 39 on one page and 40 on another"). It is 39 everywhere.
- Off-by-a-few on Elo-style numbers (AA-Briefcase, GDPval-AA) from summarizer noise.
- Wrong leaderboard ranks quoted with false precision.
- An over-broad "no page exists" assertion that was simply false. GENERAL RULE: WebFetch's summarizer is the weak link on dense numeric tables. Pull the same figure from two independent pages before recording it.

## THE NEUTRAL BACKBONE: Artificial Analysis Intelligence Index v4.3.2

Same runner, same ten evals (AA-Briefcase v1.1, GDPval-AA v2.1, AutomationBench-AA, Terminal-Bench 4.0, SciCode, Humanity's Last Exam, GDP.pdf, CritPt, AA-Omniscience, AA-LCR v1.1), every model. The only true apples-to-apples axis available. THE CEILING IS 53 (Claude Fable 5.1 max/xhigh, GPT-6 Astra max). Read every score against 53, not 100. Claude Opus 5 (max) = 51. | Model | Index | Runs on jarvis-1 | | MiMo-V2.6-Pro | 46 | blocked, no Pro GGUF | | GLM-5.3 (full) | 45 | yes today | | Qwen3.8 Max | 45 | disputed open-weight status | | Kimi K3 | 44 | no, 594 GB minimum | | GLM-5.3-Flash | 42 | fork only | | Qwen3.8-Flash-Next | 40 | yes today | | DeepSeek V4.1 Flash | 39 | *** CORRECTED Sep 24 2026: RUNTIME EXISTS IN MAINLINE. see below *** | | DeepSeek V4 Pro | 36 | no runtime anywhere | | Qwen3.8-27B (xhigh) | 34 | resident now | | K2 Horizon 375B | 31 | support intentionally not implemented | | MiniMax-M3 | 29 | 3 PRs, none merged | | Inkling | 25 | PR unmerged | | Nemotron 3 Ultra | 23 | technically yes, ~5 t/s | | K2 Horizon 7B / 3.7B | 21 / 16 | fork only | | Muse Glimmer | 19 (UNCERTAIN, two fetches gave 17 and 19) | likely | | Mistral Medium 3.5 | 14 | likely | | gpt-oss-120b | 12 | yes | | Qwen3-Coder-Next | 9 | yes today | NO AA PAGE EXISTS for Hy4-preview or Atria Dawn Preview (404s confirmed). Every number for those two is aggregator or vendor. Do not treat them as neutrally ranked.

## PER-EVAL FINDINGS THAT ACTUALLY CHANGE ROUTING

- GLM-5.3 BEATS Claude Opus 5 on two evals: AutomationBench-AA 62% vs 57%, SciCode 59% vs 56%. The open-weight gap is smaller than headlines imply.
- Qwen3.8-27B scores 6% on Terminal-Bench 4.0. Near-useless as a shell agent, despite benchlm's agentic composite putting it at 64.0% (rank 14). Trust AA over benchlm here — different composition, and the 6% is the direct measurement. Never route shell-agent work to the 27B.
- AA-Omniscience penalises CONFIDENT WRONG answers, so it goes negative. Qwen3.8-27B −10, Qwen3.8-Flash-Next −10, DeepSeek V4.1 Flash −5, GLM-5.3-Flash 7, MiMo 8, Qwen3.8 Max 12, GLM-5.3 14, Kimi K3 20, Claude Opus 5 37. EVERY local model hallucinates confidently. Standing routing rule: ground factual claims in retrieval, never in model memory.
- Flash-Next beats MiMo-V2.6-Pro AND GLM-5.3 on AA-Briefcase (1597 vs 1522 and 1525) despite a lower composite. It is stronger at business/document work than its index suggests, and weaker at terminal agents (25% vs GLM's 42%).
- Best AA-LCR (long-context retrieval) that is actually runnable today: Qwen3.8-27B at 82%, already resident, above Claude Opus 5's 79%. Kimi K3 (89%) and MiMo (86%) are higher but unrunnable.

## THE TRAPS ENCODED IN THE FILE (all six also live in models.json)

- swebench_variant (CRITICAL) — never compare SWE-bench Verified to Pro. Full detail in orchestrator-slot-plan section 4.
- aa_index_version — only compare AA scores from the same version. The 27B read 52 under an older version, 34 under v4.3.2.
- aa_ceiling — max observed is 53.
- stale_official_leaderboard — Scale's SWE-bench Pro board tops out at Muse Spark 1.1 61.50% and contains NO 2026-current open model. Newest open entries: qwen3-coder-480b-a35b 38.70, deepseek-v3p2 15.56, glm-4.6 9.67, gpt-oss-120b 16.20. Any vendor Pro claim above ~61.5% is claiming to beat the best verified result ever posted, self-run — applies to Hy4's 65.7 and marginally Flash-Next's 62.5.
- benchlm_drift_and_flags — live leaderboard, +/- 0.5 (Hy4 read 64.2 then 63.8 same day), and its open-weight flags are WRONG (marks Kimi K3 closed though unsloth ships Kimi-K3-GGUF). Ranks corrected: Hy4 rank 17, GLM-5.3 rank 22 on coding.
- aa_index_penalises_non_reasoning — Qwen3-Coder-Next's 9 is partly an artifact of being non-thinking-mode-only. Low index on a specialist model is not the same as incapable at its speciality.

## ROUTING TABLE AS DELIVERED

Interactive chat -> Qwen3.8-27B (only MEASURED model, 28.09 t/s). General all-day work -> Qwen3.8-Flash-Next. Hard reasoning, can wait -> GLM-5.3. Shell/terminal agents -> GLM-5.3 (TB4 42% vs 25% vs 6%). Tool calling/automation -> GLM-5.3 (AutomationBench 62%). Coding -> Qwen3.8-Flash-Next. Small resident code completion -> Qwen3-Coder-Next. Long-context retrieval -> Qwen3.8-27B. Science/physics -> GLM-5.3. Unsupervised factual recall -> NONE. Classification/routing -> Qwen3-1.7B with a GBNF label grammar and no shell access. THE UNRESOLVED TENSION, stated plainly in the deliverable: GLM-5.3 wins agentic, tool-calling and terminal work and runs at ~1.6 t/s. A multi-turn agent loop is impractical at that speed. Either Flash-Next proves good enough at agent work, or agentic tasks stay slow. Nothing in the data resolves this; only a measurement on the box will.

## STANDING CAVEAT

Exactly ONE model in the dataset has a measured speed on jarvis-1: Qwen3.8-27B at 28.09 t/s decode / 300.95 t/s prompt (Sep 21 2026, Q4_K_M, -sm layer, both V100s, -c 8192). Every other t/s figure in the file is an estimate from bandwidth arithmetic or other people's hardware.

## *** Sep 24 2026 — THE "FLASH TIER" HEAD-TO-HEAD, and a correction: DeepSeek V4 IS IN MAINLINE llama.cpp NOW ***

Jack asked how GLM-5.3-Flash's scores look next to "deepseek flash next". That name merges two different models — Qwen3.8-Flash-Next (what we had been discussing) and DeepSeek V4.1 Flash. Both are real and both are answered here.

### THE NEUTRAL COMPARISON (AA Intelligence Index, same ten evals, ceiling 53)

| model | index | total / active | native ctx | on jarvis-1 | | GLM-5.3-Flash | 42 | 320B / 18B | 1M | Unsloth fork, glm-5.3-flash-run-recipe | | Qwen3.8-Flash-Next | 40 | 125B (+51B n-gram) / 6B | 262K | mainline today | | DeepSeek V4.1 Flash | 39 | 552B / 16B | 1M | mainline arch exists; GGUF thin | | DeepSeek V4 Flash 0731 | 34 | 284B / 13B | 1M | DEPRECATED by DeepSeek in favour of V4.1 | The three live models sit within 3 points of each other — that is a narrow band, and AA's own article-vs-model-page inconsistency (the aa_article_vs_index_version trap above) is worth more than 3 points. Treat them as roughly equal in capability and decide on cost-per-token instead. *** THE EFFICIENCY STORY IS THE REAL ONE: Flash-Next reaches 40 on 6B active. GLM-5.3-Flash reaches 42 on 18B active — 3x the bytes read per token for 2 index points. On a bandwidth-bound box that is a catastrophic trade. *** API speed for reference (NOT transferable to jarvis-1): DeepSeek V4.1 Flash 226.6 t/s output / 0.98 s TTFT; GLM-5.3-Flash 61.4 / 3.11; Flash-Next 55.0 / 2.76.

### *** CORRECTION: "DeepSeek V4.1 Flash — no runtime anywhere" IS NOW WRONG ***

Read from llama.cpp master Sep 24 2026:

- src/llama-arch.cpp:83 — { LLM_ARCH_DEEPSEEK4, "deepseek4" } (alongside deepseek, deepseek2, deepseek2-ocr, deepseek32)
- src/llama-model.cpp:203-204 — case LLM_ARCH_DEEPSEEK4: return new llama_model_deepseek4(params);, plus is_dsv4 handling at :379 and arch cases at :2465, :2862, :2947 This supersedes the stored note that DeepSeek V4 was a WIP draft port (antirez, discussion #22376, "no intentions of merging"). Mainline carries it. BUT THE GGUF ECOSYSTEM IS THIN, WHICH IS THE ACTUAL BLOCKER NOW. HF search for DeepSeek-V4.1-Flash-GGUF returns three repos only: vcruz305/DeepSeek-V4.1-Flash-GGUF (Q2_K only, 7 shards, first shard 43,072,470,848 B → ~300 GB total, 18 likes), apetersson/...-MixedQ2-GGUF (Q2_K/IQ2_XXS, 2 likes), AMAImedia/...-FP8-GGUF (FP8 — dead on Volta). No Unsloth repo, no Q4, no KLD table. Against GLM-5.3-Flash's measured 92.22% top-1 at Q4_K_XL, a Q2-only option from a 2-like uploader is not a serious candidate. Revisit if Unsloth ships one.

### *** THE HONEST CAVEAT ON VENDOR NUMBERS, worth keeping verbatim ***

Yotta Labs' three-way comparison states it plainly: "there is no benchmark that all three models were measured on. DeepSeek reported its own suite, GLM reported Terminal-Bench 2.1 and DeepSWE, Qwen reported SWE-bench Pro and CoWorkBench. Every number is vendor-published, and the tests barely overlap." AA's index is the ONLY apples-to-apples axis across these three. Do not build a comparison table out of the vendor cards.

### WHERE EACH ONE ACTUALLY WINS, from the per-eval data already in this file

- Flash-Next: AA-Briefcase 1597, beating GLM-5.3 full (1525) and MiMo-V2.6-Pro (1522) despite a lower composite. Strongest of the three at business/document work.
- GLM-5.3-Flash: Terminal-Bench 4.0 and agentic/tool work (GLM-5.3 full posts 42% TB4 vs Flash-Next's 25%); AA-Omniscience +7 vs Flash-Next's −10 and DeepSeek V4.1 Flash's −5, i.e. it hallucinates confidently far less than either.
- VERDICT FOR JACK'S BOX: Flash-Next still wins outright. 2 index points behind GLM-5.3-Flash, but ~6-8x faster here (103.7 GiB vs 186 GiB at Q4, 6B vs 18B active, mirrorable at best quant, MTP drafts shipped in-repo, mainline support with no fork). GLM-5.3-Flash is the pick only when the specific job is terminal/tool agency or when confident-hallucination cost is high. Sources: artificialanalysis.ai model pages for glm-5-3-flash, qwen3-8-flash-next, deepseek-v4-flash, deepseek-v4-1-flash; llama.cpp master src/llama-arch.cpp and src/llama-model.cpp (read directly); HF API search for DeepSeek-V4.1-Flash-GGUF and vcruz305 repo blobs; yottalabs.ai three-way comparison.
