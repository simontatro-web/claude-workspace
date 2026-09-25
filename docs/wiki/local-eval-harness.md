# local-eval-harness

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 23, 2026).
> Cowork-only links kept as page names.
>
> Summary: Sep 23 2026 research into how to MEASURE jarvis-1 rather than guess — llama-perplexity's KL-divergence mode for quant/flag quality deltas, lm-evaluation-harness against llama-server, and promptfoo for prompt regression. This is the "measuring stick" that [[agent-harnesses]] and [[jarvis-system-gaps]] ADD 2 both ask for. Read before accepting or rejecting any tuning claim.

## *** WHY THIS IS THE HIGHEST-VALUE ITEM LEFT ***

This memory now holds roughly thirty tuning claims for jarvis-1 — -ncmoe partial offload, --cache-reuse, hyperthreaded prefill, ik_llama.cpp, the v4 CPU swap, parallel slots, extraction-before-prefill, and more. Almost none of them have been measured on his box. The stored quant decisions rest entirely on Unsloth's published tables for OTHER people's hardware. *** THE BOTTLENECK HAS SHIFTED FROM FINDING IMPROVEMENTS TO PROVING THEM. Four tools close that gap, and all four drive his EXISTING llama-server at 127.0.0.1:8080 with no new infrastructure. ***

## 1. SPEED: llama-bench — already known, already used

Covered in system-performance-levers (the tg128 calibration run and the -lm/--numa flag corrections). Use it for every speed claim. Compare aggregate throughput when testing --parallel, not per-request latency.

## *** 2. QUALITY: llama-perplexity --kl-divergence — HE CAN GENERATE HIS OWN QUANT TABLES. THIS IS THE FIND. ***

Verified in common/arg.cpp: | flag | source description | | --save-all-logits, --kl-divergence-base FNAME | "set logits file" | | --kl-divergence | "computes KL-divergence to logits provided via --kl-divergence-base" | | --ppl-stride N | stride for perplexity calculation | THE WORKFLOW: run llama-perplexity --save-all-logits ref.logits once with the highest-quality configuration he can load (the reference), then run llama-perplexity --kl-divergence --kl-divergence-base ref.logits for each candidate quant or flag set. *** WHAT THIS PRODUCES IS EXACTLY THE METRIC SET IN quant-quality-tables AND glm-5.3-quant-quality: mean KLD and top-1 token agreement. *** Those tables are currently Unsloth's numbers for Unsloth's setup. This turns "94.29% top-1 at Q4_K_XL, per the vendor" into a number measured on his own weights, his own build and his own flags. AND IT ANSWERS QUESTIONS NO VENDOR TABLE CAN: does -ncmoe partial offload change outputs at all (it should not, but prove it)? Does --cache-reuse alter results? Does ik_llama.cpp's -rtr repack stay bit-faithful as believed-but-not-documented? Does q8_0 KV cost measurable accuracy on HIS workload? Every one of those is currently an assumption in this memory.

## 3. CAPABILITY: lm-evaluation-harness — 60+ benchmarks straight at his server

There is a DEDICATED llama.cpp backend, named gguf:

```bash
lm_eval --model gguf \
    --model_args base_url=http://127.0.0.1:8080 \
    --tasks hellaswag
```

Add ,model=my-model-alias to --model_args when running in router mode.

- REQUIREMENT: "a llama.cpp release from December 2024 or newer, which returns logprobs in the modern OpenAI format (logprobs.content)". Jack is on b11089, far newer. Not a blocker.
- "Over 60 standard academic benchmarks for LLMs, with hundreds of subtasks and variants implemented."
- *** "Requests are issued concurrently" with "auto-detection of parallelism from the server's slot count" — so this benefits DIRECTLY from the batching finding in big-model-decode-prefill. Raise --parallel on llama-server and evals get dramatically faster, especially on the CPU giants where batching is nearly free. ***

## 4. PROMPT REGRESSION: promptfoo — the antidote to the silent-prompt-drift failure

Provider id llama, talks to llama.cpp's bundled HTTP server /completion endpoint, base URL defaults to http://localhost:8080, overridable with LLAMA_BASE_URL.

yaml

```bash
providers:
  - id: llama
    config:
      n_predict: 1024
      temperature: 0
      stop: ['</s>']
```

Runs prompts, asserts on responses, and compares behaviour across configurations. *** THIS IS THE TOOL ADD 2 IN jarvis-system-gaps ASKS FOR BY DESCRIPTION: the operating manual went 13 to 18 sections in one night and the knowledge-collection copy silently diverged from the live prompt, with nothing to catch it. A promptfoo suite in git, run before and after every prompt edit, makes that failure loud instead of silent. ***

## THE ORDER TO BUILD IT, AND IT IS SMALL

- Fix temperature: 0 and a fixed seed everywhere first. Without determinism none of the below means anything.
- Capture a reference logits file with llama-perplexity --save-all-logits on the current production 27B config, BEFORE changing any flags. *** That file is the baseline for every future comparison and it cannot be recreated once the config has drifted. Do this first. ***
- A ~25-item promptfoo suite of his OWN real work — ACT items, a research question, a coding task, a routing decision — committed to git. This is the "measuring stick" named in agent-harnesses. Real tasks beat academic benchmarks for deciding whether HIS system got better.
- One lm_eval task as an absolute anchor so his numbers are comparable to the outside world. Keep it small; these run long on a CPU giant.
- Then start working through the untested backlog, one change at a time, with a number attached.

## THE HONEST META-POINT

Further searching for improvements is now hitting diminishing returns. The backlog of UNTESTED claims is larger than the backlog of undiscovered ones. Every additional research pass adds to a pile nobody has measured. *** The next genuinely high-value move is not another finding, it is a baseline. *** Jack's own stated preference is evidence over reassurance, and this is the file that lets the rest of this memory meet that standard.
