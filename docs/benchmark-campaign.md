# Model benchmark campaign on jarvis-1

Started 2026-09-25. Goal (Simon): fully test and benchmark every big model and the other models on the 4 TB drive, finding each one's true maximum speed, maximum usable context and best overall configuration. Then decide what goes in which orchestrator slot.

Labels: MEASURED (on this box), SOURCE (read in code or docs), ESTIMATE, VERIFY.

## What every model gets measured on (the "model card")
Same prompts, temperature 0, fixed seed, one change per run, results saved as files on the box.

1. FIT: load time, RAM and VRAM used after load, KV cache bytes per token (read from the startup log, divided by -c).
2. SPEED: decode (tg128) and prefill (pp512, pp4096) at context depth 0, 4K, 16K, 32K and at the largest depth that fits. Report the best flag set found in the sweep, not the default.
3. MAX CONTEXT: first computed (free memory / KV per token), then PROVEN with a long real prompt at that size: the answer must use a fact placed at the start of the prompt (needle test), and the log must show truncated = 0.
4. SPECULATIVE DECODING: MTP or draft model on vs off, --spec-draft-n-max sweep, on a reasoning prompt and a copy-heavy prompt (acceptance differs a lot by content).
5. CONCURRENCY: aggregate tokens/s at --parallel 1, 2, 4 (8 for the CPU giants). For MoE models on CPU, parallel requests share expert reads, so aggregate can rise far faster than per-request speed falls.
6. QUALITY:
   - A fixed suite of ~25 of Simon's own real tasks (a research question, a coding task with tests, an ACT item with a known answer, a routing decision, a long-document question), scored against checkable answers where possible.
   - One small lm-evaluation-harness task as an outside anchor.
   - For families with several quants on the drive (27B, Flash-Next), KL divergence and top-1 agreement against the highest-quality quant, with llama-perplexity --kl-divergence.

## Flag sweeps (which knobs get tried, per model class)
- CPU models: threads 18/36 (decode) and threads-batch 36/72 (prefill); -b/-ub 512/2048/4096; flash attention on/off; K/V cache f16 vs q8_0 at depth; NUMA placement (one socket for models that fit in ~230 GiB, interleaved across both for bigger ones); load mode.
- GPU models: -ts split, single card vs both, cache type, -ub, MTP n-max; VRAM kept under ~15,300 MiB per card at load (MEASURED rule: 622 MiB free crashed).
- Hybrid (big MoE with GPU help): -ngl 99 with -cmoe, then walk -ncmoe down until VRAM is full.
- Second engine for the giants: ik_llama.cpp (-rtr, --split-mode graph, -tb) after the stock numbers exist.

## Models in scope (from /mnt/models/models)
| Model | Size | Where it runs | Needs |
|---|---|---|---|
| Qwen3.8-27B Q4_K_M (production) | 17.7 GiB | 2 GPUs | baseline for everything; downtime window |
| Qwen3.8-27B-MTP (Jackrong Q3_K_M, Q4_K_M) | 29 GB | 1 or 2 GPUs | downtime window; the single-card A/B that frees a V100 |
| HauhauCS 27B Uncensored (IQ4_XS, Q5_K_P, FastMTP draft) | 35 GB | GPU | downtime window; FastMTP draft may need its llama.cpp patch |
| Qwen3-VL-32B | 20 GB | GPU | downtime window |
| gpt-oss-20b | 13 GB | GPU or CPU | the MXFP4 test on Volta before MiMo |
| Qwen3-Coder-Next | 34 GB | GPU + CPU | downtime window |
| Qwen3.8-Flash-Next UD-Q4_K_XL + MTP drafts | 128 GB | CPU, one socket | none; runs beside Jarvis |
| Flash-Next GSQ-RCO IQ3_XXS | 71 GB | CPU, one socket | none |
| Flash-Next GSQ-RCO Q2_0 | 62 GB | CPU, one socket | none |
| GLM-5.3 UD-Q4_K_XL (MTP head present) | 468 GB | CPU both sockets, later hybrid | copied to NVMe; see docs/glm-5.3-test-plan.md |
| GLM-5.3-Flash UD-Q4_K_XL | 188 GB | CPU, one socket | Unsloth llama.cpp fork build (glm5next not in stock) |
| MiMo-V2.6-Pro MXFP4 (+ DFlash draft) | 522 GB | CPU + GPU offload, whole box | join the two raw parts (~557 GB on NVMe, so GLM copy must go first); Jarvis off; ~498 GiB resident vs 503 GiB RAM |
| Small models (router, embed, rerank, guard, HHEM, VL-4B) | slots/, embed/ | CPU | quick pass, mostly latency |

## Order (cheapest and least disruptive first)
- Phase A, Jarvis stays up: GLM-5.3 CPU runs (in progress), then the Flash-Next family on socket 1. Unattended overnight runs are fine.
- Phase B, downtime windows (Simon picks the times): all GPU models including the production baseline, GLM-5.3 interleaved and hybrid, Flash-Next with GPU help.
- Phase C, builds: Unsloth fork for GLM-5.3-Flash; ik_llama.cpp re-runs on GLM-5.3 and Flash-Next.
- Phase D: MiMo, last, because it needs the whole box and the NVMe space GLM is using.

## Time and storage (ESTIMATE)
- Deep-context prefill is the slow part: GLM-5.3 at ~15 t/s needs ~35 minutes just to fill 32K. A full GLM card is most of a day; Flash-Next a few hours per quant; GPU models an hour or two each.
- NVMe has ~377 GB free with the GLM copy. Test one big model at a time from NVMe (copy, benchmark, delete; the original stays on the drive).

## Where results go
- On the box: ~/bench/results/<model>/ (raw llama-bench JSON/CSV, logs, the card).
- In this repo: docs/benchmarks/<model>.md per model plus docs/benchmarks/summary.md, written by Claude from what Simon pastes back.

## Tools on the box (delivered 2026-09-25)
- ~/bench/bench.sh (source: docs/bench/bench.sh): runs one llama-bench sweep as a transient systemd unit bench-<label>, with GPUs hidden for CPU profiles, a 465G memory cap, no swap and OOM priority on the benchmark (not Jarvis). Profiles cpu1 / cpu / cpuil / gpu; cpuil and gpu refuse to start while llama-server is active.
- ~/bench/summary.py (source: docs/bench/summary.py): prints a table from the jsonl results.
- This llama-bench build (f4e276a20, 2026-09-21) has -d depth, -lm load mode, -ncmoe, -fitt, jsonl output. It has NO --threads-batch and no speculative decoding or --parallel, so MTP, concurrency, needle and prompt-cache tests use llama-server instead.
- Audio, video and image models on the drive (audio.cpp, ComfyUI/Wan/LTX/Hunyuan, Z-Image) are not llama.cpp text models; they need their own runtimes and a separate test pass.

## Role tests added 2026-09-25 (from Simon's orchestrator wants, docs/orchestrator-wants-simon-2026-09-25.md)
The slot decision needs numbers per ROLE, not just raw t/s. Add to each model card where it applies:
- Front desk / voice: time-to-first-token on a short prompt with a warm cache, and short-answer latency end to end. Speech needs only ~3-5 t/s, but TTFT under ~1 s.
- Spec interviewer: given 10 vague task requests, score the questions asked (coverage of a hidden checklist of what Simon actually meant) and whether the restatement adds real understanding instead of echoing.
- Router: accuracy on a labelled set of ~50 tasks (which slot should take it), plus latency. Candidates include the small router on the drive.
- Big fresh-context builder (GLM-5.3, MiMo): cold-load time from NVMe and from the USB drive (-lm dio), prefill + decode at 8K/16K/32K fresh context, since each job starts a new chat.
- Reviewer: catches planted bugs in a build, with grounding (tests, page load) available.
- Everything: hallucination checks on questions with known answers, including "I don't know" when the answer is not in context.
