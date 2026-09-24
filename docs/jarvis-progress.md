# Jarvis / Local AI / Orchestrator — Progress Notes

Pulled from a Cowork session transcript (pasted 2026-09-24). Claims below are as
Cowork reported them; not re-verified in this repo. Update as things change.

## Hardware: jarvis-1 (ASUS ESC4000, Z10PG-D16 board)

Full detail: [wiki/v100-hardware-and-models.md](wiki/v100-hardware-and-models.md)

- GPUs: 2x Tesla V100 PCIe 16GB (32 GB VRAM, Volta sm_70, 900 GB/s HBM2 each), power cap 200 W
- CPU: dual Xeon E5-2699 v3 (AVX2, no AVX-512)
- RAM: 503 GiB (16x 32GB M393A4K40BB0-CPB), runs at 1866 MT/s (2-DIMM-per-channel downclock).
  CPU-side bandwidth ~33-34 GB/s effective, the limit for anything running in RAM
- Boot: Samsung 990 PRO NVMe, fresh Ubuntu 24.04 (Sep 21 rebuild). The first NVMe died; watch SMART on big downloads
- **Hard constraints:** CUDA ≤ 12.9 (13.x drops sm_70), driver R580 (last branch for Volta),
  llama.cpp must be built from source, `-sm layer` is the only multi-GPU split mode that works on V100

## Current production setup (Sep 21, measured)

- llama.cpp b11089-f4e276a20, driver 580.178.04, CUDA 12.9
- `llama-server.service` (user simon): `ggml-org/Qwen3.8-27B-GGUF:Q4_K_M`, `-ngl 99 -sm layer -ctk q8_0 -ctv q8_0 -c 8192 --jinja`, port 8080
- **28 t/s generation**, ~300 t/s prompt (Sep 12 baseline before the rebuild: 32 t/s)
- Flash attention is compiled OUT; the vision encoder uses ~4.3 GiB on GPU0, leaving ~1.3 GiB free, so context can't be raised yet
- Unsecured: no API key, CORS open, bound to 0.0.0.0

## Model roles

- **Interactive / agentic:** Qwen3.8-27B on the GPUs. Nothing in the 32 GB class is meaningfully smarter.
- **Batch / overnight (CPU RAM, ~1.3–5 t/s):** big MoE models. As of Sep 22 on 503 GiB:
  - GLM-5.3 full: runs on the stock build today, ~2.7 t/s estimated. Jack's stated target.
  - GLM-5.3-Flash: needs a fork (3 unmerged PRs); a patched build exists at `~/glm5-llama.cpp`
  - Hy4-preview UD-IQ1_M: fits now, ~2.2 t/s estimated
  - MiMo-V2.6-Pro: no GGUF published yet
- **Small always-resident helpers:** router Qwen3-1.7B, embeddinggemma, Qwen3-Reranker-0.6B
- Later Cowork chat recommended Qwen3.8-Flash-Next (125B / 6B active, ~103.7 GiB at Q4) for the RAM
  slot, calling it ~6-8x faster than GLM-5.3-Flash. Not yet reconciled with the table above.

## Speed upgrades queued for the 27B

1. **MTP speculative decoding** (the big one): switch to a GGUF with MTP heads
   (unsloth or Jackrong, not ggml-org), `--spec-type draft-mtp --spec-draft-n-max 2 --parallel 1`.
   A 2x V100 data point hit 47 t/s. Without speculation the bandwidth ceiling is ~50 t/s
2. Rebuild with flash attention (helps prompt speed and frees VRAM for context, not decode speed)
3. ngram-mod speculation was tested and gave no gain

## What Jarvis can do today (live on jarvis-1)

- `create_tool`: writes new endpoints into `~/jarvis-tools/plugins/` and
  self-restarts the server (systemd `Restart=always`). **No approval step** (set to full auto).
- `list_tools`: returns each plugin's error text, which gives Jarvis a feedback loop to fix broken tools.
- `run_host_command`: unrestricted `subprocess.run(shell=True)`.
- Unrestricted read/write/delete over its own memory.

## Incident log

- **3x `pkill` incidents in one day.** Jarvis killed the production
  `llama-server` serving its own chat, even though its operating manual forbids that.
  Lesson: system-prompt rules don't enforce anything; use OS permissions.
- **Runaway retry.** Spent 4,666 tokens hand-rolling a GGUF parser; generation
  collapsed to 5.85 t/s, and nothing stopped it. Lesson: needs iteration and wall-clock caps.

## Self-improvement (RSI) loop plan

Jarvis already has the mutation half (self-modifying tools, self-restart, memory).
**The missing half is a scorer it cannot tamper with.**

Tiers:
1. **Prompt/scaffold optimization (start here).** GEPA on the Jarvis system prompt.
   Works with local models via LiteLLM `api_base` → llama-server :8080.
2. **Code self-modification.** Darwin Gödel Machine style: an archive of every
   version, able to branch from any ancestor. Only after the scorer has caught a real regression.
3. **Weight self-training.** Not viable: the model is too large to train, and training on
   its own outputs causes model collapse. LoRA on a 27B model is possible but not planned.

Warning: DGM faked test logs and removed hallucination-detection markers, even with
the detectors hidden. Hiding the scorer is not enough; it has to be unwritable.

### Build order (checklist)

- [ ] Capture baseline: `llama-perplexity --save-all-logits` on current production config
- [ ] Eval harness under a separate root-owned user, mode 500, outside every
      path `run_host_command` can touch
- [ ] Held-out test set the loop never sees (a train vs. held-out gap signals cheating)
- [ ] Git-backed lineage: every mutation is a commit
- [ ] Archive of all versions (not greedy best-only)
- [ ] Hard fences: loop can't touch `llama-server.service`, its own systemd unit,
      `~/.config/jarvis/` (API key, restic key), or the backup repo
- [ ] Iteration + wall-clock caps
- [ ] Tier 1: GEPA on Jarvis system prompt, scored by the harness

## Open questions / unknowns

- Orchestrator design: which models it routes between and on what rules
- Remaining Cowork pages not copied yet: jarvis-orchestrator, jarvis-system-build,
  jarvis-incidents, local-ai-setup, nvme-drive-failure, esc4000-parts-order
- Where the Jarvis source lives (not in this repo yet)
