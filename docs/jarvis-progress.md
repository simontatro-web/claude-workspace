# Jarvis / Local AI / Orchestrator — Progress Notes

Pulled from a Cowork session transcript (pasted 2026-09-24). Claims below are as
Cowork reported them; not re-verified in this repo. Update as things change.

## Hardware / box

- Host: `jarvis-1`. Bandwidth-bound (memory bandwidth limits tokens/sec), so
  **active parameters per token matter more than total size**.
- GPU note: FP8 builds are "dead on Volta", which implies Volta-generation GPU(s).
- TODO: record exact CPU / RAM / GPU / disk here.

## Model choice (local, via llama.cpp `llama-server` on :8080)

Artificial Analysis Intelligence Index (same ten evals for all):

| Model                  | Index | Total / active          | Native ctx | Notes |
|------------------------|-------|-------------------------|------------|-------|
| GLM-5.3-Flash          | 42    | 320B / 18B              | 1M         | ~186 GiB at Q4; best at terminal/tool agency; most honest (AA-Omniscience +7); 92.22% top-1 at Q4_K_XL |
| Qwen3.8-Flash-Next     | 40    | 125B (+51B n-gram) / 6B | 262K       | **Current pick.** ~103.7 GiB at Q4; MTP drafts in-repo; mainline llama.cpp; AA-Briefcase 1597 (strong at business/docs); AA-Omniscience −10 |
| DeepSeek V4.1 Flash    | 39    | 552B / 16B              | 1M         | llama.cpp mainline supports it (`LLM_ARCH_DEEPSEEK4`), but only Q2 / FP8 GGUFs from small uploaders. Revisit if Unsloth ships a Q4 |
| DeepSeek V4 Flash 0731 | 34    | 284B / 13B              | —          | Deprecated by DeepSeek |

- The three live models are within 3 points, so treat them as roughly equal on capability.
- Vendor benchmark cards barely overlap, so use the AA index as the only fair comparison.
- **Decision:** Qwen3.8-Flash-Next is the default, roughly 6–8x faster than GLM-5.3-Flash on this box.
  Use GLM-5.3-Flash only for terminal/tool-agency jobs, or where a confident
  hallucination is expensive. (Candidate routing rule for the orchestrator.)

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
- Exact hardware specs of jarvis-1
- Where the Jarvis source lives (not in this repo yet)
