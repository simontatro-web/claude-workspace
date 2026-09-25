# jarvis-model-research

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 14, 2026).
> Cowork-only links kept as page names.
>
> Summary: Slot-by-slot model research for jarvis-1 (Sep 13 2026) — router candidates, supervisor script design, GLM KV budget, retrieval corpus inspection, and model picks for coding/embedding/reranker/OCR/ASR/TTS slots. Read for model-selection/sizing questions; live build status is in [[jarvis-orchestrator]].

jarvis-orchestrator holds live build status (systemd services, job queue, coding harness); this file holds the Sep 13 2026 model-selection research that fed those decisions.

## Slot inventory, status as of Sep 13 2026

- Judge / anti-hallucination (Jack's stated top priority) — Qwen3.8-27B Q4_K_M on both V100s, MEASURED 32 t/s. Running in production as llama-server.service on port 8080. Not a separate model: the plan is a harness around the 27B (RAG retrieval → JSON-constrained answer with claims[]/sources[]/confidence → verification pass on low-confidence claims).
- Research — same 27B, different harness. Shares weights with judge.
- Vision — OPEN QUESTION RESOLVED IN PRINCIPLE: the cached ggml-org/Qwen3.8-27B-GGUF already auto-loads mmproj-Qwen3.8-27B-Q8_0.gguf and reports text+vision+video modalities, so the 27B may cover this slot natively and the separate Qwen3-VL-8B download may be unnecessary. Needs one real image test to confirm before committing either way. (Qwen-VL wants --image-min-tokens 1024 for grounding.)
- Coding — Qwen3-Coder-30B-A3B Q3_K_M (~14.7GB) picked, not yet downloaded/verified running. See the coding-model finding below, which changes this pick.
- Video — LTX-Video 2B 0.9.6-distilled (~2.3GB) picked, local-only per Jack's stated rule, not yet set up.
- Big model — GLM-5.3-Flash UD-Q4_K_XL (199.7GB), downloading Sep 13 2026 via hf download unsloth/GLM-5.3-Flash-GGUF --include "UD-Q4_K_XL/*". CPU-only, estimated ~3.5 t/s (not yet measured).
- Router — see below; picked from live-verified candidates Sep 13 2026, not yet downloaded.

## Router model candidates — VERIFIED LIVE against the HF API Sep 13 2026

Prior sessions failed because guessed HF paths didn't exist; these three were confirmed by pulling the /tree/main endpoint and reading actual file sizes:

- empero-ai/Qwen3.8-2B-Distill-GGUF — Qwen3.8-2B-Q4_K_M.gguf 1,312,164,224 bytes (1.31GB). Arch qwen35, Apache 2.0, ~705K downloads. Same arch/chat-template family as the 27B judge, so one tool-call format across the stack; Jack's build already ships ggml-vocab-qwen35.gguf, so the arch is proven on his binary. Third-party distill, so quality less certain than an official release.
- ggml-org/Qwen3-1.7B-GGUF — Qwen3-1.7B-Q4_K_M.gguf 1,282,439,264 bytes (1.28GB). Published by the llama.cpp maintainers, reference-tested path, safest sm_70 bet.
- ggml-org/Qwen3.5-0.8B-GGUF — no Q4_K_M in the repo; Qwen3.5-0.8B-Q8_0.gguf 833,592,096 bytes, Q4_0 563,036,064 bytes. Smallest/fastest option.

KEY POINT that de-risks the choice: llama.cpp's --json-schema / GBNF grammar mechanically forces valid JSON output, so the router model's JSON reliability is not a selection criterion. It only has to pick the right label, which is a classification task a 1-2B handles. Recommendation given: download both the 2B and the 1.7B (2.6GB total) and A/B them on a fixed set of ~20 routing prompts rather than committing blind.

VRAM headroom check: with the 27B tensor-split across both cards, nvidia-smi showed ~18GB of 32GB in use, so a ~1.3GB router fits on either card alongside it.

## Supervisor script — skeleton written Sep 13 2026

Delivered to Jack as jarvis-supervisor.py (257 lines, syntax-checked). Deployed and running Sep 14 2026 — see jarvis-orchestrator "SUPERVISOR DEPLOYED AND RUNNING" for live status. Design decisions:

- ONE OpenAI-compatible endpoint on port 8100 that Open WebUI points at as a single model called "jarvis"; all routing happens behind it. Avoids Open WebUI needing to know about slots.
- Slot registry as a config dict: port, gpu assignment, resident vs on-demand, model path, extra llama.cpp args, per-slot env (GLM gets NVIDIA_TF32_OVERRIDE=0, -fa off, -ngl 0).
- The production 27B on port 8080 is marked external: True — the supervisor sends requests to it but start_slot/stop_slot raise rather than manage it.
- Structural fix for the pkill class of bug (jarvis-incidents): the supervisor tracks PIDs it started in ~/.jarvis-supervisor-state.json and can only ever SIGTERM/SIGKILL those PIDs. No pkill, no name matching, explicit refusal to touch the production port. A process it did not start is by definition not its to stop.
- GPU1 worker swapping: ensure_slot stops other on-demand slots assigned to the same card before starting the requested one.
- Router failure and slot-start failure both fall back to the judge rather than erroring out.
- Response carries _jarvis_route {slot, reason} so routing decisions are visible.
- Ports chosen to avoid existing services: 8080 llama-server, 8090 browser tools, 8443 tailscale serve; supervisor 8100, router 8101, coding 8102, big 8103.
- Deps: pip3 install fastapi uvicorn httpx --break-system-packages.

WORTH CHECKING FIRST, could remove half the supervisor's job: Jack's llama.cpp build has a --models-max flag (in his settled pins), and recent llama-server versions can host multiple models with on-demand load/unload. If that works on build b10918, native multi-model serving may replace the process-management half of the supervisor. Not verified.

## GLM-5.3-Flash context/KV budget — worked Sep 13 2026

Measured starting point: free -g showed 237 GiB available after killing the leftover test processes, with llama-server, Open WebUI and the Chrome agent still running (so those are already accounted for). UD-Q4_K_XL weights are 199.7 GB decimal = 186 GiB. 237 − 186 = ~51 GiB, minus compute buffers and safety margin leaves ~40-45 GiB for KV cache. Deliberately NOT converted to a token count: GLM-5.3-Flash is 34 KDA linear-attention layers (fixed-size state, does not grow with context) plus 11 sparse-MLA layers (compressed KV), which is where the "4.44x smaller KV" claim comes from. Per-token KV could be ~20 KB or ~200 KB and that is the difference between ~200k and ~2M tokens; guessing the constant would be fake precision. MEASURE IT instead: load with a set -c and read the allocated size from the startup log (grep -iE "KV self size|kv cache|n_ctx" ~/glm_first_load.log), then scale linearly. THE BINDING CONSTRAINT IS PROBABLY NOT MEMORY: the PR's known unresolved bug collapses output into repeated garbage past roughly 60-100k context depth, so usable context is likely capped by correctness well below what RAM allows. Start at -c 32768, confirm coherence, push up only while watching for degradation. WATCH AT LOAD: GLM requires -fa off, and llama.cpp's quantized KV cache (-ctk/-ctv q8_0, which Jack uses on the 27B) generally needs flash attention for the V cache. If that combination errors, the fallback is f16 KV, which doubles per-token KV cost and halves the context budget above. Unverified, check the actual error at load.

## The retrieval corpus as it ACTUALLY exists — inspected live Sep 13 2026

Checked in Jack's Chrome at https://jarvis-1.tail7b6a92.ts.net/workspace/knowledge. There is exactly ONE knowledge collection, "jarvis memory" (id b0342885-5b9d-436b-8237-dcae65a19954), owned by Simon Tatro, 5 files, ~15.6 KB total:

- 00-README.md 797 B
- 01-operating-manual.md 4.4 KB (the same text as the model's system prompt, so it is duplicated: in the prompt AND retrievable as RAG context)
- 02-user-profile.md 2.3 KB
- 03-known-topics-index.md 4.0 KB
- 04-server-facts.md 4.1 KB CONSEQUENCE: this is an identity-and-method pack, not a knowledge corpus. It can ground claims about the server and about Jack's preferences and nothing else. An anti-hallucination harness retrieving only from this cannot verify any factual claim about the outside world, so "verified" would just mean the 27B agreed with itself. A real corpus (course documents, research, saved sources) has to be added before the harness means anything. Also confirmed live: Workspace shows Models 1 ("Jarvis", jarvis version 01), Knowledge 1, Prompts 0, Skills 0, Tools 0.

## SLOT-BY-SLOT MODEL RESEARCH — all sizes pulled live from the HF tree API Sep 13 2026

### Coding — THE FINDING THAT CHANGES THIS SLOT

Qwen/Qwen3-Coder-Next (Apache 2.0, card dated Feb 3 2026): 80B total / 3B active MoE, context 262,144, architecture is a hybrid layout with Gated DeltaNet plus Gated Attention layers. Card claims SWE-Bench Verified 70.6, SWE-Bench Pro 44.3, Terminal Bench 2.0 36.2, and "with only 3B activated parameters (80B total) it achieves performance comparable to models with 10-20x more active parameters". This is far above the planned Qwen3-Coder-30B-A3B. Sizes, unsloth/Qwen3-Coder-Next-GGUF (191,200 downloads): UD-Q2_K_XL 26.76 GB, UD-Q3_K_S 33.32 GB, UD-Q3_K_M 35.94 GB, UD-Q3_K_XL 36.28 GB, Q4_K_S 45.53 GB, Q4_K_M 48.53 GB, UD-Q4_K_XL 49.61 GB. Also ggml-org/Qwen3-Coder-Next-GGUF exists but carries only Q8_0 at 84.81 GB. ggml-org publishing it at all is evidence llama.cpp supports the architecture. WHY IT FITS JACK'S BOX DESPITE BEING 80B: only 3B active per token, so with the standard MoE offload pattern (attention and shared tensors on the V100s, expert FFN tensors pinned to CPU RAM via -ot "ffn_.*_exps.*=CPU" or --n-cpu-moe on newer builds) the CPU side reads roughly 2-3 GB per token. At his MEASURED 39 GB/s that is plausibly 13-20 t/s, while attention runs at HBM speed on GPU. This is the technique his hardware profile (little VRAM, 256 GB RAM) is ideally shaped for. ESTIMATE, unmeasured. THE GATE: Gated DeltaNet is exactly Jack's stored open question about whether llama.cpp's fused GDN CUDA path works on sm_70, and GDN-class hybrids are on the tensor-split denylist. His own free test applies directly: load it and read the startup log for the "fused Gated Delta Net ... disabled" string. The payoff is now large enough to justify running that test. FALLBACK if GDN misbehaves on Volta: unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF (12,581,343 downloads) — Q3_K_M 14.71 GB, UD-Q3_K_XL 13.81 GB, UD-Q4_K_XL 17.67 GB, Q4_K_M 18.56 GB. Plain qwen3moe, tensor-split supported, known-good. NOTE Sep 14 2026: the actual coding path built and proven this session is a different approach entirely — GVS5H, a training-free orchestration harness wrapped AROUND the existing 27B judge model (no separate coding model download needed). See jarvis-orchestrator "CODING HARNESS" and agent-harnesses. This slot's dedicated-coding-model research remains valid for later if a bigger local coding model is still wanted, but is no longer on the critical path.

### Embedding — THE HIGHEST-LEVERAGE MISSING PIECE (nothing in this slot today)

- ggml-org/embeddinggemma-300M-GGUF — single file embeddinggemma-300M-Q8_0.gguf 333,590,944 bytes (334 MB), 291,429 downloads. ggml-org published, so llama.cpp support is guaranteed. SAFE DEFAULT.
- jinaai/jina-embeddings-v5-text-nano-retrieval-GGUF — Q8_0 232.9 MB, F16 431.4 MB, plus a full i-quant ladder down to IQ1_S 99 MB. Jina publish their own GGUFs. v5 is newer and this is the retrieval-specialised variant (the family also has text-matching, classification, clustering variants — retrieval is the right one for RAG). Worth A/B-ing against embeddinggemma.
- Also live: Qwen/Qwen3-Embedding-0.6B-GGUF (107,796), ggml-org/embeddinggemma-300m-qat-q4_0-GGUF, LiquidAI/LFM2.5-Embedding-350M-GGUF, ggml-org/jina-embeddings-v2-base-code-Q8_0-GGUF (code-specific, useful if he indexes source).
- STILL AVOID Qwen/Qwen3-Embedding-8B-GGUF per the stored V100 NaN wedge (llama.cpp #26044).
- NOTE: an embedding server (ggml-org/embeddinggemma-300M-GGUF, port 8102, CPU-only) was actually built and load-tested working ({"status":"ok"}, real vectors, GPUs untouched) Sep 14 2026 per jarvis-orchestrator "STATE AT SHUTDOWN" — it just doesn't survive reboot yet (no systemd unit).

### Reranker — also missing, and it is what makes verification actually catch fabrication

- ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF (72,077 downloads) — ggml-org published, start here.
- Alternatives live: jinaai/jina-reranker-v3.5-GGUF, gpustack/bge-reranker-v2-m3-GGUF (26,429), ggml-org/jina-reranker-v1-turbo-en-GGUF.

### OCR — turns course PDFs and screenshots into corpus text (serves the schoolwork tracker)

ggml-org/DeepSeek-OCR-GGUF: DeepSeek-OCR-Q8_0.gguf 3,126,139,712 bytes (3.13 GB) plus mmproj-DeepSeek-OCR-Q8_0.gguf 447,856,768 bytes. Small enough to sit on GPU on demand. ggml-org/GLM-OCR-GGUF is the alternative.

### ASR — for the stated voice-everywhere goal

ggml-org/Qwen3-ASR-1.7B-GGUF: Q8_0 2,165,034,944 bytes (2.17 GB) plus mmproj-Qwen3-ASR-1.7B-Q8_0.gguf 355,709,344 bytes; bf16 variants also present (bf16 is pointless on Volta, use Q8_0). A 0.6B version also exists (ggml-org/Qwen3-ASR-0.6B-GGUF).

### TTS

ggml-org/Qwen3-TTS-12Hz-1.7B-Base-GGUF seen in the ggml-org listing (46,067 downloads) but NOT yet size-verified, and "Base" may need finetuning for good output. Jack's existing plan was Kokoro-82M on CPU, which is proven, tiny and commercially licensed. No reason to switch without a listening test.

### ARCHITECTURAL POINT that eases the GPU-layout conflict

The small models (embedding 334 MB, reranker ~600 MB, OCR 3.6 GB, ASR 2.5 GB) should run on CPU, not GPU. They are tiny and latency-tolerant, and CPU at 39 GB/s chews through a 300 MB model. Keeping them off the cards preserves VRAM for the models where GPU residency actually decides throughput, which partly resolves the "GPU1 is not really free" problem.

## Still open

- GPU layout conflict: the 27B judge needs both V100s (16.5GB won't fit one 16GB card), which collides with GPU1 being the free worker slot for coding/vision/video. Unresolved; the supervisor's swapping logic assumes GPU1 is available, which it is not while the 27B is tensor-split.
- The anti-hallucination RAG corpus is UNSPECIFIED and blocks the harness build — see jarvis-orchestrator "Still open" for the live version of this question.
