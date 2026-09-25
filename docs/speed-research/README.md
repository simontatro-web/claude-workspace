# Speed research: every model on jarvis-1

One standalone file per model. Each file has A (current state and limits), B (ranked levers with sources), C (a runbook of copy-paste steps for Jarvis, with SIMON ONLY steps marked), D (the proposed final config, PROPOSED until measured) and E (open questions, each with a read-only command).
Written for Simon. Labels: MEASURED (on jarvis-1, with date), SOURCE (link), ESTIMATE (arithmetic shown), VERIFY. Times are Central (CDT = UTC-5).

## Index

| # | Model | File | Best expected gain (not yet measured unless stated) | Status |
|---|---|---|---|---|
| 1 | Qwen3.8-27B Q4_K_M (Jarvis, 2x V100, MTP) | [qwen3.8-27b.md](qwen3.8-27b.md) | Decode +20-35% from tensor parallel (ESTIMATE; source run on 2x V100 measured +32% at depth 0, +40% at 32K). Prefill +20-40% from flash attention. Context 24K to 48-64K. All need a new build with FA | Runbook ready (14 steps); scripts tested offline only; nothing measured on the box yet |
| 2 | Qwen3.8-Flash-Next UD-Q4_K_XL (+ GSQ-RCO IQ3_XXS, Q2_0, MTP heads) | pending | - | next |
| 3 | GLM-5.3 UD-Q4_K_XL | pending | - | - |
| 4 | GLM-5.3-Flash UD-Q4_K_XL | pending | - | - |
| 5 | MiMo-V2.6-Pro MXFP4 (+ DFlash draft) | pending | - | - |
| 6 | 27B-MTP (Jackrong), HauhauCS 27B, Qwen3-VL-32B, gpt-oss-20b, Qwen3-Coder-Next | pending | - | - |
| 7 | Small models (router, embedders, rerankers, guard, judge, VL-4B) | pending | - | - |

## Conventions used by every runbook
- Test folders Jarvis may write to: `~/speed/` (scripts, results, downloads) and new build trees `~/llama.cpp-<name>/`. The production `~/llama.cpp`, systemd units, Open WebUI, the NVIDIA driver and BIOS are SIMON ONLY.
- Anything long runs as a systemd unit (`sudo systemd-run --unit=... -p User=simon -p Group=simon ...`), never nohup. Test processes get MemoryMax, MemorySwapMax=0 and OOMScoreAdjust=1000.
- Before any benchmark or big-model load, this must print NONE-ACTIVE:
  `systemctl list-units --type=service --state=active --no-legend --plain | grep -E '^(bench-|mtp-test|il-beside|glm-test|fn-test|t27-|big-verify|build-|dl-)' || echo NONE-ACTIVE`
- Quality rule: lossless levers first. Speculative decoding and any numerics change (flash attention, tensor parallel, new build) must give greedy output identical to the reference, or differ first at a near-tie token (reference top-2 logprob gap ≤ 0.10 nats) with equal scores on the fixed quality set. Lossy levers (smaller quant, quantized KV, shorter reasoning) need a measured gate first: llama-perplexity KLD against the current quant with top-1 ≥ 99% and mean KLD ≤ 0.01, or equal scores on Simon's quality suite.

## Scripts (docs/speed-research/scripts/)
| File | Lines | Bytes | sha256 (first 16) | What |
|---|---|---|---|---|
| j27_logstats.py | 77 | 3,464 | fb7817288dbaffa2 | Read-only: summarises llama-server speed, draft acceptance, prompt-eval times and truncations from the journal (output under 2,500 characters) |
| t27_window.py | 390 | 22,533 | 05d965589667b06d | SIMON ONLY: downtime-window tester for the 27B. Stops Jarvis, tests named configs on port 8081 (speed, VRAM peak, output identity and near-tie gaps, quality set), always restores Jarvis |
| deliver-27b.sh | 476 | 26,642 | b24fe79be242015f | Paste-in delivery of the two files above by heredoc, with checksum check |

## Limits of this research session
- huggingface.co, medium.com, hackmd.io and some blogs were blocked by this session's network policy, so Hugging Face file lists and model cards were read through search-result summaries, not directly. Every runbook step that downloads from Hugging Face lists the files and checks sha256 on the box first.
- llama.cpp facts were read from the source at the production commit f4e276a20 and at master 4b1a27f (2026-09-25).
