# finetuning-and-rpc-pooling

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 23, 2026).
> Cowork-only links kept as page names.
>
> Summary: Sep 23 2026 research into two capabilities jarvis-1 has never explored — training LoRA adapters locally on the V100s (and serving them hot-swappable from llama-server), and pooling RAM across machines with llama.cpp's RPC backend to raise the model-size ceiling. Read before assuming the box can only run other people's weights, or that 503 GiB is a hard model ceiling.

Companions: local-model-landscape (Volta constraints), llama-server-live-unit, learning-partner and act-study-site (the use cases an adapter would serve), jarvis-what-not-to-do.

## *** PART 1: HE CAN TRAIN HIS OWN ADAPTERS. THIS CAPABILITY HAS NEVER BEEN CONSIDERED ANYWHERE IN THIS MEMORY. ***

Every model decision on file has been about which of OTHER PEOPLE'S weights to download. Fine-tuning a LoRA adapter on his own data is a separate axis entirely, and the hardware supports it.

### UNSLOTH EXPLICITLY SUPPORTS VOLTA

Unsloth's own requirements page: "Minimum CUDA Capability 7.0 (V100, T4, Titan V, RTX 20 & 50, A100, H100, L40 etc)". V100 is named. (It also notes GTX 1070/1080 "works, but is slow.") VRAM by model size, from the same page: | model | QLoRA (4-bit) | LoRA (16-bit) | | 7B | 5 GB | 19 GB | | 8B | 6 GB | 22 GB | | 70B | 41 GB | 164 GB | Interpolating, a 27B QLoRA lands around 17-20 GB — which EXCEEDS one 15.77 GiB V100, and Unsloth's multi-GPU story is weak. *** SO THE REALISTIC TARGET ON THIS BOX IS A 7-9B ADAPTER, NOT A 27B ONE. *** A 7B QLoRA at 5 GB fits one card with enormous room; a 9B is comfortable. That matches the models already in his library (Qwen3.5-9B class, the MiMo 9B distill, gpt-oss-20b is borderline).

### *** BUT THE STATED SUPPORT AND THE BUG TRACKER DISAGREE. CHECK BEFORE BUDGETING TIME. ***

- unsloth issue #1336, "V100 does not work" (Nov 25 2024, Tesla V100-SXM2-32GB): crashes at model init with a Triton assertion, "Unexpected srcLayout in ReduceOpConversion" in ReduceOpToLLVM.cpp, core dumped. Labelled "fixed - pending confirmation" with no confirmation recorded. Contributing factors noted: kernel 5.4.0 below the recommended 5.5.0, CUDA 12.2, Triton 0.0.28.
- unsloth issue #4082, "V100 cannot perform full fine-tuning of BF16 models" — the same Volta theme running through this entire memory. Volta has no bf16. *** THE RULE IS THE SAME ONE AS EVERYWHERE ELSE ON THIS BOX: force fp16, never bf16. *** Any training config that defaults to bf16 will fail on sm_70. Expect to set fp16=True / bf16=False explicitly, and expect a Triton version dance.

### *** THE PART THAT MAKES THIS ACTUALLY USEFUL: llama-server SERVES ADAPTERS, AND CAN HOT-SWAP THEM ***

Verified from common/arg.cpp on master: | flag | behaviour | | --lora FNAME | "path to LoRA adapter (use comma-separated values to load multiple adapters)" — multiple adapters at once | | --lora-scaled FNAME:SCALE,... | per-adapter weighting | | --lora-init-without-apply | loads adapters WITHOUT applying them, so they can be switched per request at runtime via the API | | --control-vector FNAME | steering vectors | *** CONSEQUENCE: one resident base model plus several small adapters, switched per request, with NO model reload. *** On a box where reloading the 27B costs minutes and both V100s, that is the difference between "specialised models" being impossible and being nearly free. Natural adapters for his actual work: one trained on ACT item style (act-study-site, jarvis-act-generator), one on his own writing voice, one on his research-note format. --control-vector is the cheaper cousin worth trying FIRST: steering vectors need no training run at all, just contrastive prompt pairs, and they cost nothing to produce. If the goal is tone or refusal behaviour rather than new knowledge, try this before spending GPU hours.

### HONEST LIMITS

- A LoRA teaches STYLE AND FORMAT far more reliably than it teaches FACTS. For "know my stuff", retrieval (deep-research-optimization) beats fine-tuning and is already most of the way built.
- Training occupies the V100s, so it competes directly with the production 27B and with video generation. It is another entry for the mutual-exclusion scheduler rule in jarvis-what-not-to-do rule 21.
- Nothing here is measured on his box. Unsloth's claimed V100 support plus two open-ish V100 bug reports is exactly the "stated support vs actual" gap that needs one real test run before planning around it. Test with a 7B QLoRA on a tiny dataset first; do not start with a 9B and a real corpus.

## *** PART 2: THE 503 GiB CEILING IS NOT ABSOLUTE — llama.cpp CAN POOL RAM ACROSS MACHINES OVER RPC ***

tools/rpc/README.md, read directly. ggml-rpc-server exposes a host's devices to a main host over TCP; "If there are no accelerators, it exposes a single CPU device", so plain RAM on another machine counts. Build both sides with -DGGML_RPC=ON, then llama-server ... --rpc 192.168.x.x:50052,192.168.x.y:50052.

- "By default, llama.cpp distributes model weights and the KV cache across all available devices, both local and remote, in proportion to each device's available memory", overridable with --tensor-split.
- Local cache: ggml-rpc-server -c stores large tensors on the remote host "to avoid transferring them over the network. This can speed up model loading significantly", in $HOME/.cache/llama.cpp/rpc or wherever LLAMA_CACHE points. Without this, every start re-ships the weights across the wire.
- RDMA transport is supported and auto-negotiated (Linux RoCEv2 via libibverbs; macOS Thunderbolt 5), falling back to TCP. GGML_RPC_NO_RDMA=1 forces TCP. Jack has ordinary ethernet, so TCP it is.
- Debug with GGML_RPC_DEBUG=1.

### WHY THE NETWORK IS NOT THE OBVIOUS DISASTER IT LOOKS LIKE

RPC ships activations, not weights (once the weights are resident or cached on the remote). A hidden state for a 6144-wide model is ~12 KB per token per boundary, not gigabytes. So per-token wire traffic is trivial even on gigabit; the real cost is LATENCY, one round trip per cross-machine layer boundary.

### *** THE VERDICT FOR JACK TODAY: KNOWN, EVALUATED, NOT WORTH IT YET. ***

- The maintainers' own warning, verbatim: the RPC backend is "currently in a proof-of-concept development stage... the functionality is fragile and insecure. Never run the RPC server on an open network or in a sensitive environment!" On a box that already hosts an unrestricted shell tool server, that is a real consideration, not boilerplate.
- His other machines do not have meaningful RAM to add. The Windows desktop and the laptop are ordinary consumer machines; adding 16-64 GiB to 503 GiB does not unlock anything. Kimi K3's smallest quant needed ~610 GB against his 503 — roughly 110 GB short, which no consumer desktop closes. SO: record it, do not build it. *** REVISIT IF EITHER OF TWO THINGS HAPPENS: he acquires a second large-RAM machine, or a model he genuinely wants lands just past 503 GiB. *** There is real precedent that it works at that scale: cpu-moe-speed-levers already records a user running Nemotron 3 Ultra as a 2-bit GGUF across 2x DGX Spark via llama.cpp RPC at ~5 t/s.
