I'm Simon. This session is a DEEP RESEARCH pass on speeding up every model on my home AI server, jarvis-1, WITHOUT losing quality. The output must be runbooks my local assistant Jarvis can execute directly when I copy and paste them into its chat. Another Claude Code session is running live benchmarks on the box; do not touch its work.

SETUP
1. Run: git fetch origin claude/new-session-uyo1y3 && git checkout -b claude/speed-research origin/claude/new-session-uyo1y3
   Commit and push ONLY to claude/speed-research. Never push to claude/new-session-uyo1y3. Do not edit docs/HANDOFF.md, docs/bench/ or docs/benchmarks/ (read them only).
2. Read in full: docs/HANDOFF.md (box, rules, current state), docs/jarvis-briefing-2026-09-25-part5.md (verified box facts, wins on conflicts), docs/benchmark-campaign.md (model list), docs/benchmarks/*.md (MEASURED numbers so far), docs/speed-levers.md (the lever list so far), docs/glm-5.3-test-plan.md, docs/bench/* (the scripts already on the box), docs/wiki/README.md and every wiki page relevant to the model you are on.
3. Re-fetch claude/new-session-uyo1y3 before starting each model (git fetch, then read docs/benchmarks/ from origin/claude/new-session-uyo1y3) so you use the newest measured numbers.

THE TASK
Go through the models ONE AT A TIME, in this order, each as a completely independent pass (do not carry conclusions from one model to the next unless you re-verify them for this model):
 1. Qwen3.8-27B Q4_K_M (Jarvis's production model, 2x V100 16 GB, with its MTP draft)
 2. Qwen3.8-Flash-Next UD-Q4_K_XL (+ GSQ-RCO IQ3_XXS and Q2_0, + MTP heads)
 3. GLM-5.3 UD-Q4_K_XL
 4. GLM-5.3-Flash UD-Q4_K_XL
 5. MiMo-V2.6-Pro MXFP4 (+ DFlash draft)
 6. Qwen3.8-27B-MTP (Jackrong Q3_K_M / Q4_K_M), HauhauCS 27B (IQ4_XS / Q5_K_P + FastMTP), Qwen3-VL-32B, gpt-oss-20b, Qwen3-Coder-Next
 7. The small models (router, embedders, rerankers, guard, judge, VL-4B)
For each model, research EVERY way to make it faster (decode, prefill, long context, time-to-first-token, concurrency, load time) on THIS hardware: 2x Xeon E5-2699 v3 (Haswell, AVX2, no AVX-512), 503 GiB DDR4-1866 (2 DIMMs per channel), 2 NUMA nodes, 2x Tesla V100-PCIE-16GB (sm_70, CUDA toolkit must stay <= 12.9), Ubuntu 24.04, stock llama.cpp f4e276a20 plus the builds already on the box (llama.cpp PR #28243 worktree at ~/llama.cpp-fnmtp, ik_llama.cpp at ~/ik_llama.cpp, sm70-attn). Cover: engine flags; other engines and community forks (ik_llama.cpp, KTransformers, vLLM/SGLang/ExLlama where they can run on Volta or AVX2, NUMA-mirror forks, expert-cache PRs, DSA/sparse-attention work); speculative decoding (MTP, draft models, n-gram, EAGLE, DFlash); CPU/GPU placement (-ot, -ncmoe, split modes, tensor split); KV cache types; prompt caching and slot save/restore; batching and --parallel; OS/BIOS levers (NUMA, THP/hugepages, governor, memory interleave, snoop mode); build flags; smaller or better-repacking quants ONLY with measured quality numbers; and hardware upgrades as a separate costed list.
Do real deep research: GitHub PRs, issues and discussions (check merge state and dates), Hugging Face model cards and discussions, the engines' docs and source, r/LocalLLaMA and similar reports from comparable hardware. Give a link for every external claim. Prefer levers that are merged, maintained and measured by someone on similar hardware. Say plainly when something does not apply to Volta, AVX2 or this RAM size.

QUALITY RULE ("without losing quality")
- Lossless levers first (same weights, same math): flags, engines, placement, speculative decoding, caching, OS tuning.
- Speculative decoding must be verified: greedy output identical to the non-speculative run, OR any difference shown to be a near-tie token with equal answer quality on a fixed quality set. Note: on this box MTP outputs differed from MTP-off at a near-tie token, identically across n-max 1-3 (see docs/benchmarks/qwen3.8-flash-next.md); design the check accordingly.
- A lossy lever (smaller quant, quantized KV cache, pruning, shorter reasoning) needs a measured gate before adoption: llama-perplexity --kl-divergence against the current quant with top-1 agreement >= 99% and mean KLD <= 0.01, or equal scores on the quality suite. State the gate in the runbook.

OUTPUT (one file per model, standalone)
docs/speed-research/<model-slug>.md, plus docs/speed-research/README.md (index: model, file, best expected gain, status). Any helper script goes in docs/speed-research/scripts/ with its line count, byte count and first 16 hex characters of sha256 computed by you.
Each model file has:
 A. Current state: measured numbers with dates (from docs/benchmarks), current flags, and what limits speed (with the arithmetic).
 B. Ranked lever table: lever / expected gain (ESTIMATE with source) / quality risk / needs downtime? / effort / evidence links.
 C. RUNBOOK: numbered steps, one lever per step, in the order to try them. Each step must be executable by Jarvis from a copy-paste, which means:
   - Each step is ONE fenced block, under 3,500 characters in total, headed "JARVIS STEP <model>-<n> of <N>: <title>", and fully self-contained (Jarvis may run it in a fresh chat with no other context).
   - It states: goal; preconditions to check first (with the exact read-only command and the expected result); the exact commands; how long it takes; the expected output; a PASS/FAIL rule with numbers; how to undo it; and a save_finding line recording the result.
   - Commands must be short (Jarvis's 27B breaks tool-call JSON on long strings): no heredocs, no file contents longer than a few lines. Anything longer is a script in docs/speed-research/scripts/ that I (Simon) deliver by terminal heredoc with checksums; mark that part "SIMON STEP".
   - Jarvis's tools cap output at 4,000 characters (run_host_command stdout/stderr, read_file returns only the LAST 4,000 characters): every command must print a short summary (use tail, grep, head, or summary.py), never a raw log.
   - Anything long-running runs as a systemd unit (sudo systemd-run --unit=NAME -p User=simon -p Group=simon ...), never nohup, with a MemoryMax, MemorySwapMax=0 and OOMScoreAdjust=1000 on the test process.
   - Anything that stops or restarts llama-server (Jarvis itself), touches the production unit, the open-webui container, the NVIDIA driver, BIOS, or anything outside the test folders is marked "SIMON ONLY - Jarvis must not run this" (Jarvis cannot safely stop itself), and must include a backup and a test on a spare port first.
   - Only one big model in RAM at a time, and only when no other benchmark unit is active (check systemctl is-active bench-queue mtp-test il-beside and any glm-test / bench-* unit first).
 D. The final recommended config once the steps pass (the exact command line), clearly marked as PROPOSED until measured.
 E. Open questions and VERIFY items, each with the exact read-only command that would settle it.

RULES
- Call me Simon. Older notes and files on my model drive call me "Jack"; that is me, but never use that name. "Jackrong" is a Hugging Face uploader, not me.
- Times in Chicago (Central) time.
- Label every claim MEASURED (on my box, with date), SOURCE (with link), ESTIMATE (show the arithmetic) or VERIFY. Accuracy over reassurance: say plainly when something is wrong, unmeasured, or will not work here.
- Never recommend pkill/killall; stop things with systemctl or a confirmed PID. Nothing gets deleted without my yes. Changes to the box are my decision: runbooks are proposals I choose to paste.
- You cannot reach jarvis-1 and must not give me commands to run in this session; everything goes into the runbooks.
- No model identifiers in commits or files.
- Commit and push after EACH model's file is done, so nothing is lost if the session ends. Update docs/speed-research/README.md each time.

When you have read everything, reply with a short plan and any questions, then start with model 1.
