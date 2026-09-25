# glm-5.3-flash-run-recipe

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 23, 2026).
> Cowork-only links kept as page names.
>
> Summary: Sep 24 2026 — the actual working way to run GLM-5.3-Flash on jarvis-1 with both speed and accuracy. The Unsloth fork branch that works, the measured KLD/top-1 quant table, why UD-Q4_K_XL is the only sane pick, the NUMA-mirror fit that costs no quality, the long-context OOM workaround, and the fork-exclusivity catch. Read before building or running Flash.

Companions: cpu-moe-speed-levers (at size cap), big-model-decode-prefill (MTP findings), context-and-speed-per-model, quant-quality-tables, jarvis-what-not-to-do. Jack Sep 24 2026: "how do i run glm 5.3 flash with speed and accuracy, there has to be a way." There is. This file is that way. It supersedes the pessimistic "no lane / three stalled PRs / architecture unmerged everywhere" framing in cpu-moe-speed-levers and model-tier-ceiling.

## *** THE BUILD: UNSLOTH'S OWN FORK. NOT MAINLINE, NOT THE THREE ABANDONED PRs. ***

Unsloth publishes an official run-locally guide with exact commands:

```bash
git clone --branch glm5next/upstream https://github.com/unslothai/llama.cpp
```

cmake llama.cpp -B llama.cpp/build -DBUILD_SHARED_LIBS=OFF -DGGML_CUDA=ON

```bash
cmake --build llama.cpp/build --config Release -j --clean-first \
      --target llama-cli llama-mtmd-cli llama-server llama-gguf-split
```

This fork is ACTIVELY MAINTAINED, which is the thing the old memory got wrong. unslothai/llama.cpp PR #217 (danielhanchen) is titled "Repin GLM-5-Next onto the head carrying the indexer softmax fix" — they are tracking upstream and carrying architecture fixes. MAINLINE IS STILL NOT THE ROUTE, re-confirmed Sep 24: src/llama-arch.cpp master lists chatglm, glm4, glm4moe, glm-dsa — no glm5next. And mainline PR #27752 is still a DRAFT whose author states the 288-expert stacking, FP8 weight_scale_inv dequant and the NextN block "have never been exercised on the real checkpoint" (their dev machine has 128 GB against a 328 GB checkpoint). Do not build from #27752, #27754 or #27773. CUDA note for Jack: keep -DGGML_CUDA=ON with -DCMAKE_CUDA_ARCHITECTURES=70 for the V100s.

## *** THE QUANT TABLE — MEASURED KLD AND TOP-1, PUBLISHED BY UNSLOTH. THIS IS THE ACCURACY HALF OF THE QUESTION. ***

| quant | size | top-1 accuracy | mean KLD | | UD-IQ1_S | 93.09 GB | 70.89% | 0.669714 | | UD-IQ2_XXS | 101.84 GB | 76.30% | 0.450148 | | UD-Q2_K_XL | 108.72 GB | 78.34% | 0.380134 | | UD-IQ3_XXS | 120.37 GB | 81.63% | 0.283772 | | UD-Q4_K_XL | 199.71 GB = 186.0 GiB | 92.22% | 0.049294 | *** THE CLIFF IS BRUTAL AND IT DECIDES EVERYTHING: Q4_K_XL's KLD is 5.8x BETTER than IQ3_XXS for 79 GB more. *** Every quant below Q4 loses 10-21 points of top-1. On a box with 503 GiB there is no reason to ever run Flash below UD-Q4_K_XL. Anyone recommending IQ3/IQ2 is optimising for a 128 GB machine, which is not this one.

## *** THE LUCKY PART: THE BEST QUANT IS ALSO THE MIRRORABLE ONE. NO ACCURACY/SPEED TRADE EXISTS HERE. ***

186.0 GiB fits one socket (~251 GiB) with ~65 GiB spare. Two copies = 372.0 GiB against 503 GiB. NUMA mirroring is viable AT FULL Q4 QUALITY. This is the opposite of GLM-5.3 full, where cpu-moe-speed-levers proved no quant is both mirrorable and good (mirroring needs 870 GiB; the largest socket-fitting quant is UD-Q2_K_XL at 80.93% top-1). Flash is the one big model where the speed lever is free of quality cost. That is the answer to "speed AND accuracy." Mirror gain is measured elsewhere at 1.47x (Qwen 122B MoE) and 1.63x (dual-socket R740); the forks (vproxy-tools/llama.cpp GGML_NUMA_MIRROR, ik_llama --numa mirror discussion #2030) are unmerged — that is the real cost, not quality.

## *** REAL-WORLD ANCHOR, FIRST ONE FOUND FOR FLASH ON A RAM-BOUND BOX ***

From unsloth/GLM-5.3-Flash-GGUF discussion #4: a user on 176 GB system RAM + RTX 3090s, bottlenecked on dual-channel DDR5-4800, reports:

- 108k context: prefill 60-70 t/s, generation 6-7 t/s
- 240k context: prefill 8-11 t/s, generation 6 t/s
- 1M context: "a slog" CALIBRATION: dual-channel DDR5-4800 is ~76.8 GB/s theoretical. Jack's measured effective is ~36.6-39 GB/s, roughly half. So expect ~3-3.5 t/s unmirrored, ~5-6 mirrored — which corroborates the independent bandwidth arithmetic already on file (3-4 / 5-7) rather than replacing it. Note their prefill collapses 6-8x from 108k to 240k. Prefill, not decode, is what makes long context unusable — same conclusion as every other model here.

## *** THE LONG-CONTEXT OOM HAS A REPORTED WORKAROUND. THIS RETIRES THE "OOM AT ~32k" BLOCKER. ***

The flag is real: common/arg.cpp:2687 defines {"-lm", "--load-mode"} with values auto, none, mmap, mlock, mmap+mlock, dio. Users report CUDA OOM during token GENERATION, not prefill, above 262,144 tokens of context, even when the model fit VRAM at load. One user: "Stable now with --load-mode none" in place of mmap+mlock. *** CONSISTENT WITH model-storage-plan's RESIDENCY RULE AND jarvis-what-not-to-do: mlock on a model that is not comfortably resident converts a graceful slowdown into a hard failure. *** BUT IT IS A TRADEOFF, NOT A FREE FIX: none disables mmap, so the whole 186 GiB is read into RAM up front — slower startup, no page-cache sharing across processes. Fine here because 186 GiB genuinely fits; do NOT copy this flag to a model that relies on paging (MiMo especially, where it would be fatal). Try it first on any Flash OOM before concluding the architecture is broken. NOTE the reported OOM threshold is ~262k, while ik_llama PR #2376 has a SEPARATE unresolved OOM at ~32k prompt. Different fork, different bug. --load-mode none is evidence for the 262k one only.

## *** THE ACCURACY LEVER ALMOST NOBODY MENTIONS: reasoning_effort ***

Unsloth's own run line:

```bash
--temp 1.0 --top-p 0.95 --chat-template-kwargs '{"reasoning_effort":"max"}'
```

reasoning_effort accepts low / high / max. Max context 1,048,576. *** THIS CONFLICTS WITH JACK'S temperature: 0 OPEN WEBUI ROW, exactly as MiMo does. *** temp 0 is a 27B-specific MTP-acceptance tweak. Give Flash its own model row: temp 1.0, top_p 0.95. For code (DeepSWE-style) the vendor suggests temp 0.95 / top_p 1.0 instead.

## *** THE CATCH, AND IT IS THE REAL ONE: THE FORKS ARE MUTUALLY EXCLUSIVE ***

Three separate forks each hold one lever, and they are different codebases — you cannot have all three in one binary without merging them yourself: | lever | where it lives | status | | glm5next architecture (works, maintained) | unslothai/llama.cpp glm5next/upstream | the build above | | MTP self-speculative, 1.43x MEASURED ON CPU | ik_llama.cpp PR #2399 | OPEN, blocked on PR #2376 | | NUMA mirror (~1.5x) | vproxy-tools fork / ik_llama #2030 | unmerged | | glm5next + MTP draft-cache fix, MERGED | turbo-tan/llama.cpp-tq3 PR #82 (commit 32cf4cb, Sep 17) | merged in THAT fork | SO THE HONEST STACK IS: pick the Unsloth fork and get a working, accurate Flash at ~3-3.5 t/s today; the ~5-7 t/s mirrored and ~7-10 t/s mirrored+MTP figures require fork-merging work nobody has done for you. Do not promise the stacked number as if it were one git clone.

## THE RUN LINE TO START FROM

```bash
llama-server -m GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf
  --load-mode none                     # NOT mmap+mlock -- the OOM workaround
  -ngl 99 -ncmoe <tune>                # partial expert offload, see [big-model-decode-prefill](#melange-wiki:big-model-decode-prefill)
  --numa distribute                    # + numactl --interleave=all
  --threads 36 --threads-batch 72      # physical for decode, logical for prefill
  -b 4096 -ub 4096                     # prefill only, ~2x, free
  --jinja                              # REQUIRED for tool calling
  -lv 4                                # once, to catch silent full-prompt reprocessing
```

Sampling in the client, not the server. Stop the 27B first if offloading.

## STILL TRUE, DO NOT LOSE THESE

- KDA hybrid linear attention is the HIGH-RISK case for prompt-cache breakage (prompt-cache-and-prefill-reuse). Multi-turn agentic use could reprocess the whole prefix every turn and eat the entire speed win. Test with -lv 4 and watch time-to-first-token across turns before building anything on Flash.
- Flash scores 42 on the Artificial Analysis index vs GLM-5.3 full's 45. A quality step down from full, independent of quant. *** CAVEAT: AA's own X account has posted "GLM-5.3-Flash scores 57", contradicting AA's own website (42, confirmed across three pages). Almost certainly an index-version rescale. CITE THE 42-vs-45 GAP, NOT THE ABSOLUTE NUMBER. ***
- The HF model card points at llama.cpp PR #27754, while #27752 is the one that verifiably exists with the matching title and author. Neither is the route (both unlanded); noted so a card link does not send anyone down the wrong path.
- unslothai/llama.cpp PR #217 is MERGED, not pending — the indexer softmax fix is already on the glm5next/upstream branch. That branch is the settled route, not a moving target.

## *** BLIND VERIFICATION Sep 24 2026: 100% (12/12), ZERO ERRORS. ***

An adversarial auditor checked all 15 numbers in the quant table, both build commands, the arch-entry absence in mainline master, PR states and quoted author text, the 176 GB user's four throughput figures, the --load-mode flag definition at common/arg.cpp:2687, and every arithmetic step. Its own note: "I went in expecting to find fabrications and did not find any." The five flags it raised were nuance, not error, and are all folded in above. This is the first section of this memory to clear Jack's 95% bar outright.

- Flash-Next still beats it on this box (6B active vs Flash's ~18B active; ~18-27 t/s stacked). Flash is the pick only if its 42-index reasoning is specifically wanted.
- Nothing here is measured on jarvis-1.

Sources: unsloth.ai/docs/models/glm-5.3-flash (build commands, KLD table, sampling); huggingface.co/unsloth/GLM-5.3-Flash-GGUF (+ discussion #4 for the 176 GB anchor and the --load-mode none workaround); github.com/unslothai/llama.cpp PR #217; ggml-org/llama.cpp PR #27752 (draft status) and master src/llama-arch.cpp; ikawrakow/ik_llama.cpp PR #2376 and #2399; turbo-tan/llama.cpp-tq3 PR #82.
