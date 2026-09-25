Jarvis — this is a state briefing from Claude, relayed by Simon. Simon wants you to store it in your memory so you know everything going on with this box and the plan. Do NOT act on anything in it yet — no installs, restarts, edits or downloads. Just save it.

HOW TO SAVE IT (follow exactly):
1. Use write_file to create ~/jarvis-memory/briefing-2026-09-25.md containing everything between the lines "=== BEGIN BRIEFING ===" and "=== END BRIEFING ===" below, verbatim. Write it in 3 calls to keep each call short: first call (append=false) = from the "# Jarvis state briefing" title through the end of PART 1; second call (append=true) = the whole "## PART 2" section; third call (append=true) = the whole "## PART 3" section through "END OF BRIEFING".
2. Use read_file on it and confirm the last line is "END OF BRIEFING". Report total_lines and the sha256_12 from the last write.
3. Append (append=true, never overwrite) this one line to ~/jarvis-memory/state.md: "2026-09-25: full state briefing from Claude in ~/jarvis-memory/briefing-2026-09-25.md — read it before any model, server, orchestrator or download work."
4. Reply with: the byte count, line count, and a 5-bullet summary of what you learned. Run no other commands.

=== BEGIN BRIEFING ===
# Jarvis state briefing — 2026-09-25 (from Claude's notes up to Sep 24 2026)

Trust labels: MEASURED = measured on jarvis-1. ESTIMATE = arithmetic or other people's hardware, not measured here. VERIFY = Claude cannot see the box; check it yourself before relying on it. These are Claude's notes, not ground truth — where the live box disagrees, the box wins, and tell Simon.

## PART 1 — THE BOX, THE LIVE SERVER, THE TOOLS, THE RULES

### Hardware
- ASUS ESC4000 G3. 2x Xeon E5-2699 v3 (Haswell, 18 cores each, AVX2, NO AVX-512). 503 GiB RAM, 16x32 GB at DDR4-1866, ~251 GiB per socket. Measured effective memory bandwidth ~36.6-39 GB/s.
- 2x Tesla V100-PCIE-16GB (Volta sm_70): ~16,144 MiB usable each. No bf16, no fp8, fp16 only. Both cards on PCIe gen3 x16, topology PHB, both on NUMA node 0 (CPU affinity 0-17,36-53). MEASURED.
- Boot drive: 990 PRO NVMe, 915G, ~54G used, ~815G free (Sep 23). Has a history of spare-pool worries — watch available_spare, media_errors, critical_warning.
- Wall power: on a 120 V / 15 A circuit, near the ceiling at full load. Simon does NOT care about electricity cost — never raise cost. Circuit capacity still matters: do not run a GPU video render at the same time as a two-card LLM load.
- NVIDIA driver 580 is the LAST branch that supports Volta. A jump to 590+ would brick inference. It should be pinned with apt-mark hold. VERIFY whether it is pinned.

### The production model (llama-server.service, port 8080) — MEASURED Sep 23
Qwen3.8-27B Q4_K_M (ggml-org), both GPUs, build 0.4.1-dev b11089 commit f4e276a20. Flags:
-hf ggml-org/Qwen3.8-27B-GGUF:Q4_K_M -ngl 99 -sm layer -ts 28,36 -ctk f16 -ctv f16 -c 24576 --host 0.0.0.0 --port 8080 --jinja --chat-template-kwargs '{"reasoning_effort":"xhigh"}' --no-mmproj --no-reasoning-preserve --spec-type draft-mtp -md /home/simon/models/mtp-Qwen3.8-27B-Q4_0.gguf --spec-draft-n-max 5 --spec-draft-p-min 0.4 -devd CUDA0 -ngld 99 --parallel 2 --kv-unified
Prefixed with numactl --cpunodebind=0 --membind=0 (VERIFY). Backup of the unit before xhigh: /etc/systemd/system/llama-server.service.pre-xhigh.
Weights: ~/.cache/huggingface/hub/models--ggml-org--Qwen3.8-27B-GGUF/snapshots/efbb3b1f.../Qwen3.8-27B-Q4_K_M.gguf. Find live model files with: sudo grep -i gguf /proc/<pid>/maps (the fd list is empty after mmap).

DO NOT "FIX" THESE — each was measured:
- f16 KV, not q8_0: q8_0 KV was the entire 49% slowdown. f16 gave +69% long generation. Never recommend q8_0 KV on this server without flash attention.
- --spec-draft-n-max 5: higher is strictly worse (acceptance collapses past 5).
- -ts 28,36: deliberate VRAM balance. An even split caused a crash (a card at 622 MiB free core-dumped Sep 22).
- --spec-draft-p-min 0.4: +10% on reasoning, but about -5 to -9% on copy-heavy work. Only open question: re-test with p-min removed to confirm it is the sole cause.
- xhigh reasoning costs ~3.3x the thinking tokens of low (not throughput). Override per request with chat_template_kwargs when a fast answer matters.
- Power limit 200 W: 250 W measured identical (noise). Do not revisit.

Speeds: ~/bench.py <port> gives short ~51.2 t/s, copy-heavy ~65.6 t/s — this is a NEW baseline, not comparable to older figures (83.7 t/s on a 3,500-token generation, ~500 t/s prefill, from different scripts). Always discard the first bench run after a start (reads ~6% low). /tmp is wiped on reboot.
VRAM under load: GPU0 can peak with only ~728 MiB free. Keep each card under ~15,300 MiB used.

### Boot, power and ECC — MEASURED Sep 23
- Old bug FIXED: nvidia-powercap.service caused a systemd ordering cycle, so llama-server silently never started after a reboot (signature: enabled, inactive, ZERO journal lines). nvidia-powercap is now disabled; gpu-tune.service (persistence mode + -pl 200, Before=llama-server) owns GPU settings. Verified across a reboot.
- ECC is currently DISABLED on both cards and it freed ZERO VRAM (V100 HBM2 has no ECC cost). Recommendation: turn it back on (sudo nvidia-smi -e 1, then reboot) — it is the only early warning on old HBM. Simon's decision.
- /props lies about MTP ("speculative.types": "none" even when MTP works). Judge MTP from journalctl (common_speculative_init_result) and VRAM, not /props.

### Open WebUI
- Container open-webui, must be -p 3000:8080 (the app listens on 8080 inside). A 3000:3000 mapping took the whole UI down twice. docker needs sudo on the rebuilt box (VERIFY). Never hand-write a docker run for it; never stop/rm/restart it yourself — that cuts Simon off from you.
- The "jarvis" model row: temperature 0, num_ctx 24576 (must always equal llama-server -c), function_calling native, builtin_tools False, plus a system-prompt line to prefer write_file. Preserve all of these in any edit.
- Tool server connection lives in the config table, key tool_server.connections. The spec is fetched live (no cache). That row contains the bearer key — always redact it when printing.
- Tailscale Funnel was ON (Open WebUI public on the internet) and was turned OFF Sep 15. `tailscale serve status` should show tailnet only. VERIFY it is still off.

### Your tool server — port 8200 (jarvis-run-host-commands.service, ~/jarvis-tools/main.py)
Endpoints: run_host_command (output clipped to first 1500 + last 2000 chars with a TRUNCATED marker; env JARVIS_TOOL_HEAD / JARVIS_TOOL_TAIL), write_file, read_file (paged), save_finding (appends to ~/jarvis-memory/findings/<slug>.md), web_search (DuckDuckGo), hf_model_sizes (many repos in one call), create_tool and list_tools (plugins in ~/jarvis-tools/plugins/, the server restarts itself ~3 s after create_tool). Every call is logged to ~/jarvis-run-host-commands.log. The API key is in ~/.config/jarvis/run-host-commands.env — never print it (it was leaked once and rotated).
Simon chose a fully unrestricted shell. Do not add restrictions he declined. Simon also wants you to keep full control of your own memory.

### Open safety items (Simon's decisions, not yours)
1. Port 8200 binds 0.0.0.0 = an unrestricted shell exposed to the whole LAN. Suggested fix: bind to 172.17.0.1 (the docker0 gateway Open WebUI uses). Not done.
2. After the Sep 21 rebuild, the guardrail sections of your system prompt may not have come back: §13 Stopping processes, §14 Docker/container operations, §19 Never cut Simon off. VERIFY by reading your own system prompt later, and tell Simon if any are missing.

### Rules you must follow (from real incidents on this box)
- Never pkill, killall or kill by name pattern. Identify by PID (ps -p <pid> -o pid,ppid,etime,rss,cmd) and systemctl status. Stopping production llama-server needs Simon's explicit yes, and you must say plainly it takes you offline. Three pkill incidents on Sep 13 killed production.
- Never give Simon, or run, anything that removes his ability to talk to you (Open WebUI container, port mapping, llama-server) without saying so plainly.
- Anything multi-line: write_file, then one short run_host_command. No heredocs through the shell tool (JSON-quoting failures past ~700 chars).
- Same lookup across many items: write ONE looping script, don't make 82 tool calls. Aim for under 10 tool calls per turn.
- Prefer existing tools over hand-rolling (the GGUF-parser runaway on Sep 21). If a task keeps failing, stop and ask Simon.
- Back up any file before editing it. Test on a spare port (8081/8099), never by editing the production unit. A foreground test server must fully exit (kill by PID) before production restarts, or production OOM-loops.
- Any -c change → update num_ctx in Open WebUI to match.
- Never state a rate derived from a coarse counter (available_spare moves in whole percents) as a verdict.

## PART 2 — WHAT EXISTS, WHAT IS DOWNLOADED, HOW TO RUN THE BIG MODELS

### Before vs after the Sep 21 rebuild — VERIFY
Before Sep 21 this box had: ~/jarvis.db + job API on 8110 (jarvis-api/worker/notify units), a healthcheck, a supervisor on 8100, an embedding server on 8102, the GVS5H coding harness in ~/coding-harness/GVS5H, ntfy push (topic in ~/.ntfy-topic), and the ACT math tool server on 8103 (~/jarvis-act-math). After the rebuild the home dir only had llama.cpp, models/, sftp-repo, mem.txt and the restic key. Assume these are GONE unless you find them. Check later with ls and systemctl list-units 'jarvis*' and report.
Also on the box now: ~/sm70-attn (the flash-attention fork for V100, separate build, production untouched), ~/fa-test.sh (runs it on port 8099), ~/bench.py.

### The download drive (fast house)
A 4 TB USB drive, D:\models, on Simon's Windows PC (desktop-9ii55td) at the fast house, driven by D:\models\CHAIN.ps1 (logs in D:\models\_logs\chain.log). As of Sep 24 14:00Z about 1,821 GB was done:
- pull.py DONE: HauhauCS uncensored Qwen3.8-27B Q5_K_P + FastMTP-32K draft + its patch, HauhauCS IQ4_XS; Qwen3.8-Flash-Next (ISTA-DASLab GSQ-RCO IQ3_XXS and Q2_0, unsloth UD-Q4_K_XL, unsloth MTP/ folder); GLM-5.3-Flash UD-Q4_K_XL; GLM-5.3 full UD-Q4_K_XL; MiMo-V2.6-Pro-RL MXFP4 (2 raw parts) + DFlash-Q8_0 draft; gpt-oss-20b.
- pull_extras DONE: Wan 2.2 / LTX 2.5 / HunyuanVideo 1.5 video models, Z-Image, Qwen3-Coder-Next, embedding/reranker/OCR/ASR models. pull_hq mostly done (upscalers).
- Running or queued then: addendum (Qwen3-VL-32B, Kokoro, audio models), corpora (Wikipedia, PMC, PubMed, arXiv, Gutenberg, etc.), data, wants, wheels, pull_orch (Jackrong Qwen3.8-27B-MTP Q3_K_M + Q4_K_M, HHEM-2.1-Open, Qwen3-VL-4B, deberta prompt-injection, Qwen3Guard-Gen-4B, Qwen3-1.7B router, Qwen3.8-2B distill), pull_research (Qwen3-Reranker-4B, Qwen3-VL-Reranker-2B, SimpleQA, RAGTruth, FRAMES, HotpotQA, MuSiQue, docling). Final state unknown — ask Simon.
Nothing from this drive is on jarvis-1 yet (VERIFY). Checksum against the HF sha256 before trusting a file.

### Governing speed facts
- Decode t/s ≈ memory bandwidth ÷ bytes read per token. On CPU that is ~37 GB/s ÷ (active params × bits/8). Prefill (prompt reading) is the real bottleneck for every big CPU model and has not been measured for any of them here. Comparable hardware manages 16-44 t/s prefill, so a 32K prompt can mean 15-30 minutes before the first word.
- Never use a big model one request at a time interactively. Queue work and run several requests concurrently (--parallel N): MoE models share expert reads across a batch.
- Big models need the 27B STOPPED to use the GPUs; they cannot co-reside with it on the cards. Only one giant at a time in RAM.
- Useful flags for CPU giants: --threads 36 --threads-batch 72 (physical for decode, hyperthreads for prefill), -b 4096 -ub 4096 (prefill), --numa distribute, -ngl 99 -ncmoe N (keep the first N layers' experts on CPU, the rest on GPU; tune N down until VRAM is full), --jinja (required for tool calling), -lv 4 once to see "forcing full prompt re-processing" (it is hidden at default verbosity).
- mmap is on by default. NEVER --mlock a model that is not comfortably resident (turns slowdown into OOM kill).

### Qwen3.8-Flash-Next — the best big model for daily use
125B total / 6B active, AA index 40 (27B is 34). Supported in mainline llama.cpp since PR #27742 — check: grep -ril qwen4exp ~/llama.cpp/src/.
Quants: GSQ-RCO IQ3_XXS 70.6 GiB (quality pick), GSQ-RCO Q2_0 61.9 GiB (3.4x faster prefill, a bit weaker on code), unsloth UD-Q4_K_XL 103.7 GiB (insurance; known to pair with the unsloth MTP drafts). ESTIMATE ~10-17 t/s, ~18-27 with MTP. Fits one socket. Risks: its Gated DeltaNet prefill on CUDA is slow (run CPU-heavy); prompt caching across turns may break — test with -lv 4 before building anything on it. Very verbose. It is also the coding pick (SWE-bench Pro 62.5 vs Qwen3-Coder-Next 44.3).

### GLM-5.3 full (UD-Q4_K_XL, 435 GiB) — capability ceiling, slow
AA index 45, 753B / 40B active, top-1 94.29% at this quant. Runs on the current stock build (arch glm-dsa). Fits RAM with ~68 GiB spare; the KV cache is compressed (MLA), ~88 KiB/token → ~813K tokens possible. ESTIMATE ~1.5-2 t/s raw, ~2.5-4 optimized. It spans both sockets and cannot be NUMA-mirrored at this quant. On first load: check whether tensor blk.78.nextn.eh_proj.weight exists (then --spec-type draft-mtp gives ~1.3-1.6x), and read the KV size from the startup log. Best at terminal/tool work (Terminal-Bench 42%) and science. Ask-one-hard-question model.

### GLM-5.3-Flash (UD-Q4_K_XL, 186 GiB)
AA 42, 18B active, top-1 92.22%. NOT in mainline. Build Unsloth's fork: git clone --branch glm5next/upstream https://github.com/unslothai/llama.cpp, build with -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=70. ESTIMATE ~3-3.5 t/s. Use --load-mode none (fixes a long-context OOM; it fits RAM). Sampling: temp 1.0, top_p 0.95, reasoning_effort "max" — give it its own Open WebUI row, not temp 0. Earlier PR notes said NVIDIA_TF32_OVERRIDE=0 and -fa off may be needed — check. Do not trust past ~60K context (degradation bug). High prompt-cache risk.

### MiMo-V2.6-Pro (MXFP4, 518.9 GiB) — highest index (46), tightest fit
Join the two raw parts on the 990 PRO (needs ~634 GB free): cat MiMo-V2.6-Pro-RL-MXFP4.gguf.part2 >> MiMo-V2.6-Pro-RL-MXFP4.gguf.part1 && mv ...part1 MiMo-V2.6-Pro-RL-MXFP4.gguf. The file is ~16 GiB bigger than RAM, so it only fits with -ngl 99 -ot "ffn_.*_exps.*=CPU" (experts in RAM ~466 GiB, the rest on both GPUs) → ~489 GiB RAM. The 27B must be stopped. Draft: -md MiMo-V2.6-Pro-RL-DFlash-Q8_0.gguf --spec-draft-n-max 7. Sampling temp 1.0, top_p 0.95 (own Open WebUI row). No vision in this file. ESTIMATE ~2-3 t/s, ~4-5 with the draft. Run gpt-oss-20b FIRST as a cheap test of MXFP4 on these GPUs.

### Uncensored 27B (HauhauCS Q5_K_P, 18.8 GiB)
Same base model as production, so the tuned flags carry over. Needs both GPUs, so it swaps with production (~3 min each way). Its FastMTP-32K draft REQUIRES HauhauCS-FastMTP-llama.cpp.patch (else a 248320 vs 32768 vocab mismatch), pinned to llama.cpp commit 4df29be4f4c3673f428170fda944a5b19f743bb8 — a separate build. IQ4_XS (14.63 GiB) fits one card as a fallback. Its quality/"0 refusals" claims are unverified.

### Freeing a GPU (the re-layout plan)
-sm layer uses one card at a time, so a 27B that fits ONE card loses little speed and frees the other V100. Plan: A/B Jackrong Qwen3.8-27B-MTP Q3_K_M (12.57 GiB) on port 8081 against production; check its MTP tensors first. If it works, GPU1 is free for video or a second model.

### Model rankings to remember (Artificial Analysis index v4.3.2, ceiling 53)
MiMo-V2.6-Pro 46, GLM-5.3 45, GLM-5.3-Flash 42, Qwen3.8-Flash-Next 40, DeepSeek V4.1 Flash 39, Qwen3.8-27B 34, Qwen3-Coder-Next 9. Rank models by the score AT THE QUANT THAT FITS, not at full precision. Terminal-Bench 4.0: 27B only 6% → never route shell-agent work to the 27B. Every local model hallucinates confidently (27B AA-Omniscience -10) → ground factual claims in retrieval, never model memory. Never compare SWE-bench Verified with SWE-bench Pro.

## PART 3 — THE PLANS, DEAD ENDS AND PRIORITIES

### Orchestrator design (agreed)
- Four layers: state (SQLite), workers (systemd units + timers), tools (FastAPI), interfaces (Open WebUI chat/voice, ntfy push). The model is a component, not the system.
- Small models are independent systemd units; the supervisor is proxy-only and never kills processes.
- Router: Qwen3-1.7B on CPU, output forced to a fixed label set with a GBNF/JSON-schema grammar, logprobs as confidence, NO tools and NO shell. Route to PIPELINES (chat, queued coding job, retrieval answer, overnight research), not just models.
- Filters: HHEM-2.1-Open (cross-encoder, transformers with trust_remote_code, CPU) gates every RAG answer and research claim. deberta-v3 prompt-injection classifier on every web page before a tool-holding model reads it. Qwen3Guard-Gen-4B for any public-facing endpoint. Qwen3-VL-4B reviews websites after builds — console errors and DOM checks are ground truth, the VLM is the weakest link.
- Small models (embedding, rerankers, OCR, ASR, router) run on CPU to keep VRAM free.
- Coding: GVS5H ledger harness around the fast model (proved 27B 69→92% on LiveCodeBench-hard in the paper) as a queued job, never interactive. Harness the FAST model, not the giant.

### Research pipeline (spec on the drive: D:\models\RESEARCH-SPEC.md)
Scoping interview (6-8 questions; "what would change the answer?") → research brief in SQLite with a hard budget → query matrix → per document: fetch (Chrome/CDP or local ZIM/PMC) → extract with trafilatura (80% fewer tokens; never use an LLM to extract) → router triage → rerank → Flash-Next extracts claims as JSON with verbatim quotes → HHEM gate. Once per night: GLM-5.3 full synthesis, review by a different model, 27B polish. Output is a CLAIM TABLE; numbers are never paraphrased; always include "what I could not establish". Search: free academic sources and local corpora first; Serper/Tavily free tiers as fallback; SearXNG is broken, skip it. Throughput ESTIMATE: 2,000-3,000 documents per night. A local model cannot self-verify to a 95% bar — this makes research auditable, not frontier-accurate. Run long jobs as systemd user units with linger, never tmux.

### Video (local only, Simon's rule)
PyTorch cu126 wheel ONLY (2.11 dropped sm_70 elsewhere), pinned. Never fp8 checkpoints. Start with Wan 2.2 (only family proven on V100), add the 4-step LoRAs (~5x faster), then I2V-A14B Q5_K_M. LTX-2.5 only if audio is wanted. Check every first render for NaN/black frames; flash attention for V100 is a known NaN source for LTX — add it last. Generate 480p/720p, upscale 2x (FlashVSR fast, SeedVR2 quality, batch size 5/9/13). Target 1080x1920 vertical. ESTIMATE ~3-5 min per 5-second clip; overnight batch job, one GPU, while the LLM is stopped unless the re-layout frees a card.

### Measure before changing anything (the highest-value next step)
1. Fix temperature 0 + fixed seed. 2. Save reference logits NOW with llama-perplexity --save-all-logits on the production config (cannot be recreated once config drifts); later compare with --kl-divergence. 3. A ~25-item promptfoo suite of Simon's real tasks in git, run before and after every prompt edit. 4. One small lm_eval task (--model gguf, base_url http://127.0.0.1:8080).

### Dead ends — do not propose again
q8_0 KV on production; draft-n-max above 5; even tensor split; -b 4096 on production; turning ECC off for VRAM; 250 W; overclocking or vBIOS flashing; TensorRT-LLM, ExLlamaV3, vLLM ≥0.20, ik_llama.cpp on CUDA, ktransformers, Ollama (all broken on V100); GGML_CUDA_ENABLE_UNIFIED_MEMORY; SearXNG; LLM-based page extraction; Hy4-preview (dropped); Kimi K3 (too big); GLM-5.3 IQ1_S (too low quality); RPC RAM pooling (not now); slot save/restore on the hybrid 27B (loses checkpoints). -sm tensor is blocked because flash attention does not resolve on the stock build for this model.

### Unfinished experiments
- sm70-attn fork: +41% prefill and cheap long context, but -24% decode vs an old baseline that used a different script. Owed: identical scripts against production, and the fork with -fa off. Until then do not ship it.
- p-min 0.4: remove only that flag and re-bench to confirm it causes the copy-heavy drop.
- Prompt cache on the 27B: run once with -lv 4 and --cache-reuse 256 and watch time-to-first-token across turns. Loading an mmproj disables cache reuse, so vision should be a separate slot.

### Priority list (Simon decides the order)
1. Safety: bind port 8200 to 172.17.0.1; confirm guardrail sections §13/§14/§19 are in the system prompt; confirm Funnel is off.
2. Baseline measurements (above) before any tuning.
3. Re-enable ECC; pin driver 580.
4. When the drive comes home: checksum, copy, join MiMo, run gpt-oss-20b, test Flash-Next (with -lv 4), then GLM-5.3, then MiMo.
5. Rebuild the state/job/notify stack if it is gone; add an Open WebUI health check (port 3000 → 200) — the UI was down 20 minutes once with no alert.
6. Router + HHEM + embedding/reranker as CPU units; then the research pipeline.
7. Jackrong single-card A/B to free a GPU; then video.
8. A plug-in energy meter to size a UPS (a 900 W UPS is too small at full load).

END OF BRIEFING
=== END BRIEFING ===
