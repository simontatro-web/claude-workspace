# model-download-manifest

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 23, 2026).
> Cowork-only links kept as page names.
>
> Summary: The Sep 23 2026 list of exactly which models Jack is downloading, their verified sizes, total time/space, and which house each runs at. Read before starting any model download or planning the fast-house trip. Split out of [[model-storage-plan]], which hit its size cap.

Companion to model-storage-plan (the drive and hot/cold tiering), glm-5.3-download (why GLM must be re-pulled), qwen38-flash-next, mimo-v2.6-feasibility, cpu-moe-speed-levers.

## THE SITUATION

- Home line: 4.1 MB/s measured (home-internet-speed). Other house: 500 Mb/s ≈ 45-55 MB/s real. Roughly a 12x difference.
- Target drive: Models (D:), NTFS, 3726 GB, Seagate SkyHawk 4TB in a Vantec NexStar TX, plugged into a Windows-on-ARM64 laptop ("seaturtle").
- Jack asked for Hy4-preview AND MiMo in addition to the first two. All of it fits.

## THE MANIFEST

| Item | Size | Note | | Qwen3.8-Flash-Next UD-Q4_K_XL | 111.3 GB | TOP PRIORITY. Runs on stock build b11089 TODAY (PR #27742 merged Aug 27). 6-10x faster than GLM-5.3. Index 40 vs GLM 45. | | Qwen Flash-Next MTP draft GGUFs | ~4 GB | Free speculative decoding, same repo, no vocab-matching hunt | | GLM-5.3 UD-Q4_K_XL | 467 GB | Capability ceiling (index 45), but only 1.6-4 t/s | | MiMo-V2.6-Pro SOURCE repo | 573.5 GB | No Pro GGUF exists; this is safetensors for local conversion | | Hy4-preview IQ1_M | ~219 GiB / ~235 GB | Size taken from the mirror table in cpu-moe-speed-levers — CONFIRM against the repo tree before trusting it | | gpt-oss-20b | ~12 GB | The cheap mxfp4 test. Same MXFP4 code path as MiMo on Volta, 12 GB instead of 534 GiB. Run it BEFORE committing to any MiMo conversion. | TOTAL ≈ 1,390 GB against 3,726 GB → fits with ~2.3 TB spare. TIME at the fast house: ~7.7 h at 50 MB/s, ~6.2 h at a full 62.5 MB/s. One overnight visit covers all of it.

## SPLIT BY LOCATION

TONIGHT, AT HOME (4.1 MB/s): start Qwen3.8-Flash-Next only — 111 GB ≈ 7.5 h, one overnight run. It is the highest-value model per GB and the only one that runs on the stock build today. Doing it here frees the entire fast-house visit for the other four. AT THE FAST HOUSE: GLM-5.3, MiMo source, Hy4-preview, gpt-oss-20b. ≈ 1,280 GB ≈ 7 h.

## *** USE A SYSTEMD UNIT, NOT tmux ***

tmux is what died last time and left no forensic trail (see glm-5.3-download — 242 GiB lost, tmux ls came back "no server running", log frozen at 0%). Any multi-hour download on jarvis goes in a systemd user unit with loginctl enable-linger, logging with timestamps to a file.

## THE MiMo CONVERSION IS UNBLOCKED BY THIS DRIVE — that was the point of buying it

Source (534 GiB) on the HDD, GGUF output (~498 GiB) on the 990 PRO, which df showed at 766 GB free on Sep 23. The old "short by ~170 GiB" blocker only existed while both were assumed to land on the NVMe.

## HONEST CAVEATS ON THE TWO JACK ADDED (expectation-setting, not objections — he is getting them anyway)

- Hy4-preview: its best quant STQ1_0 (ternary) is still blocked — the AVX2 kernel PR is unmerged, and bitnet.cpp/T-MAC do NOT unblock it (they only run natively-trained BitNet models). So the runnable option is IQ1_M, a very aggressive quant, and i-quants are the compute-hungriest on AVX2-without-AVX-512. ik_llama.cpp has no hy_v4 support either. No CPU-only benchmark for it exists anywhere — nobody has posted one.
- MiMo-V2.6-Pro: mxfp4 is VERIFIED working on Volta CUDA (DP4A path) and AVX2 CPU, and conversion PR #29257 merged Sep 22. But no Pro GGUF exists, so this is a source download plus a local conversion. CHECK FOR A COMMUNITY Pro GGUF RIGHT BEFORE THE TRIP — kernelpool already published a Flash MXFP4 GGUF, so a Pro one may follow, which would replace 573.5 GB plus a conversion with a ~498 GiB direct download. Expect ~3.3 t/s: a "ask one hard question, come back after dinner" model, not an agentic builder.

## VERIFY BEFORE LEAVING THE FAST HOUSE

Checksum each model against HuggingFace's published SHA256 while still on the fast line. A corrupt shard found there is a ten-minute refetch; the same shard found at home is hours or days.

bash

```bash
curl -s "https://huggingface.co/api/models/<repo>/tree/main/<folder>?expand=true" \
  | python3 -c "import json,sys;[print(f['lfs']['sha256'], f['path'].split('/')[-1]) for f in json.load(sys.stdin) if f.get('lfs')]"
```

## *** Sep 23 2026 — JACK'S PROPOSED FINAL LIST, REVIEWED AND AMENDED. APPROVED WITH FOUR ADDITIONS. ***

Jack proposed: Hy4-preview 1-bit quant, GLM-5.3 full, GLM-5.3-Flash, Qwen3.8-Flash-Next, MiMo-V2.6-Pro, and "maybe" the uncensored Qwen3.8-27B. VERDICT: the list is sound. One item should be promoted from "maybe" to certain, and three small things are missing.

### THE AMENDED LIST, IN DOWNLOAD PRIORITY ORDER (do them in this order so an early exit still leaves the best stuff)

| # | Item | Size | Why this rank | | 1 | Qwen3.8-Flash-Next UD-Q4_K_XL | 111.3 GB | Runs on stock build b11089 TODAY. Best capability-per-hour on the list. | | 2 | Flash-Next MTP draft GGUFs | ~4 GB | MUST HAVE. This is the lever that takes Flash-Next from ~10 t/s to 18-27 t/s. Same repo. Downloading Flash-Next without these is leaving 2x on the table. | | 3 | Uncensored Qwen3.8-27B — RentedNoodle GSQ-RCO-IQ3_XXS-Uncensored-MTP | 10.4 GB | *** PROMOTE FROM "MAYBE" TO CERTAIN. *** It is 0.6% of the download and it is the ONLY item on the whole list that meets Jack's stated ~50 t/s interactive bar (anchor: 47.3 t/s measured on 2x V100 for this quant family). Everything else here is a slow model. It fills the V100 freed by the GPU re-layout. | | 4 | Qwen3.8-27B MTP quant — Jackrong/Qwen3.8-27B-MTP-GGUF Q3_K_M | ~13.5 GB | MISSING FROM HIS LIST. Required for the single-card re-layout in orchestrator-slot-plan that frees the second V100 in the first place. | | 5 | gpt-oss-20b | ~12 GB | MISSING. The cheap MXFP4 test — same code path as MiMo on Volta, 12 GB instead of 534 GiB. Run it BEFORE committing to a MiMo conversion. | | 6 | GLM-5.3 full UD-Q4_K_XL | 467.3 GB | The capability ceiling he can actually load (index 45). | | 7 | MiMo-V2.6-Pro source repo | 573.5 GB | Highest index (46). Needs local conversion; check for a community Pro GGUF first. | | 8 | Hy4-preview UD-IQ1_M | 235.4 GB | Take IQ1_M, NOT Q4_K_M. Q4_K_M is 435.2 GiB and would run at ~1.3 t/s, the slowest thing on the box. | | 9 | GLM-5.3-Flash UD-Q4_K_XL | ~200 GB | Archive only. No lane (see model-tier-ceiling finding 6). Worth having if the PRs ever revive; do not plan a slot around it. | TOTAL ≈ 1,627 GB against 3,726 GB → fits with ~2.1 TB spare. ~9 hours at 50 MB/s. ITEMS 1-5 TOTAL ONLY ~151 GB ≈ 50 MINUTES. That is the "if I only get an hour" set, and it contains everything that actually runs well today.

### WHY THE UNCENSORED 27B IS THE BEST VALUE ON THE WHOLE LIST

Every other model here is in the 1.3-27 t/s range. Jack said his interactive floor is ~50 t/s and that the current Jarvis speed is "perfect". The uncensored 27B is the only item that lands in that band, it costs 10.4 GB, it has MTP inside the file (not a separate draft), it ships its own evals/ directory, and GSQ-RCO is the same quant family as the 47.3 t/s measurement. Do not treat it as optional.

### WHAT WAS CONSIDERED AND LEFT OFF, with reasons

- Hy4 Q4_K_M (435.2 GiB) — worse than useless here: same footprint as GLM-5.3 but 49B active vs 40B, so ~1.3 t/s. Take IQ1_M.
- Hy4 STQ1_0 (229.4 GB) — the README documents CUDA support and no CPU/AVX2 kernel. His Hy4 would be CPU-resident. Skip.
- A smaller GLM-5.3 quant (UD-Q2_K_XL, 236 GiB) — it WOULD fit one socket and be NUMA-mirrorable, but top-1 drops 94.29% → 80.93%. Jack's stated constraint for the capability tier is no quality sacrifice. Skip.
- DeepSeek V4.1 Flash — now has PRs and a GGUF, but 16B active = ~4 t/s on this box, slower than Flash-Next for a lower index. Skip.
- Kimi K3 — smallest GGUF 594 GB > 503 GiB RAM. Cannot run at any quant.

## *** Sep 23 2026 — ADD TO THE FAST-HOUSE LIST: HauhauCS Uncensored 27B Q5_K_P. Jack picked this repo and this quant, and chose to wait for the fast house rather than pull it at home. ***

Repo: HauhauCS/Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-MTP-GGUF (Apache 2.0). Sizes pulled live from the HF API Sep 23 2026. | Pull this | Exact filename | Bytes | | the model | Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-Q5_K_P.gguf | 20,218,177,664 (20.22 GB) | | the draft | Qwen3.8-27B-Uncensored-HauhauCS-Aggressive-FastMTP-32K.gguf | 903,453,952 (903 MB) | | the patch — GRAB IT | HauhauCS-FastMTP-llama.cpp.patch | 2,445 | | also small | HauhauCS-RELEASE-MANIFEST.json (4,828), FastMTP-PROVENANCE.json (882), .sig (64) | — | Skip mmproj BF16 (931 MB) — Jack runs --no-mmproj. Do NOT take Q8_K_P (31.46 GB) or Q6_K_P (25.92 GB): they exceed the ~31.5 GiB of usable VRAM across both cards before draft or KV. Not loadable. Jack's choices: Q5_K_P, and it lives in a SEPARATE SLOT — production Qwen3.8-27B stays as is. He rejected IQ4_XS and Q4_K_P. TIME: 20.22 GB at the home line's 4.1 MB/s is ~82 minutes; at the fast house it is under 10. That is why it is on this list.

### SAME BASE MODEL AS PRODUCTION, so every tuned flag should carry over

README architecture: base Qwen/Qwen3.8-27B, 64 layers (48 Gated DeltaNet + 16 gated-attention), hidden 5,120, FFN 17,408, vocab 248,320, native ctx 262,144. Identical to the model Jack runs, so the -ts 28,36, MTP, -c, KV and sm70-d256 findings in llama-server-live-unit should transfer. Q5_K_P is 18.8 GiB of weights vs the current 17.66, so expect slightly less KV headroom. VRAM sanity: 18.83 GiB weights + 0.84 GiB draft = 19.67 GiB of ~31.5 GiB usable, leaving ~11.8 GiB for KV and compute buffers. At the ~123 MiB per 1k tokens measured for f16 KV under FA, that is a large context. Confirm on first load, do not assume.

### *** THE THING TO RESOLVE ON ARRIVAL: FastMTP SHIPS A llama.cpp PATCH, AND ITS NECESSITY IS UNSETTLED ***

HauhauCS-FastMTP-llama.cpp.patch modifies src/models/qwen35.cpp. What it does: FR-Spec-style draft-vocabulary trimming — detects a d2t (draft-to-token) tensor, sets n_vocab_out to the smaller draft vocab, sizes the output tensor to n_vocab_out instead of n_vocab, and at inference expands the trimmed logits back to full vocab through the d2t map, filling unused slots with -inf. A read of the patch describes it as an optimization with graceful fallback when d2t is ABSENT. DO NOT TREAT THAT AS SETTLED FOR THIS FILE. The fallback covers a draft with no d2t. This repo ships the patch precisely because its own FastMTP GGUF is expected to CARRY d2t — and an unpatched llama.cpp, not knowing the tensor, would size the output tensor at full n_vocab and hit a dimension mismatch at load. So the patch is plausibly REQUIRED for this specific draft, not optional. HOW TO SETTLE IT IN ONE COMMAND ON ARRIVAL — dump the draft's tensors and look for d2t:

bash

~/sm70-attn/build/bin/llama-gguf \<FastMTP file> r n 2>&1 | grep -i d2t

\# or: python3 -c "import gguf, sys; ..."  / gguf_dump, already known-working on this box

d2t present → apply the patch to the fork and rebuild before expecting the draft to load. d2t absent → the stock path works and the patch is genuinely optional. The patch targets a file that exists in the sm70-attn fork (it is llama.cpp), so applying it there is plausible, but the fork tracks a different commit — expect a possible rebase of a 2.4 KB patch, which is trivial.

### CLAIMS FROM THE README THAT ARE MARKETING, NOT MEASUREMENTS — verify before believing

- "K_P" quants are a custom scheme by this uploader, claiming quality equal to one or two tiers higher for 5-15% more size. No published KLD or perplexity. IQ4_XS and IQ3_M in the same repo are standard formats with known behaviour; the K_P line is not.
- "FastMTP delivers up to 3.02x document / 1.93x reasoning throughput" — uploader's own figure, untested on this box. Jack's existing unsloth MTP head already gives a measured ~2.5x, so the incremental gain may be small.
- "Zero refusals across 465 test cases" — uploader's claim, unverified.
- The draft is named **FastMTP-32K, suggesting it is trained for 32K context. Whether speculation acceptance degrades past 32K is UNKNOWN and matters, since the whole point of the FA work is contexts well beyond that. Test acceptance at 24K vs 49K+ before planning a long-context slot around it.

## *** Sep 23 2026 — BLIND VERIFICATION PASS CHANGES THIS MANIFEST. READ BEFORE THE TRIP. ***

### *** DROP OR RE-DECIDE ITEM 7: MiMo-V2.6-Pro (573.5 GB) HAS NO PAYOFF — THE MODEL DOES NOT FIT IN RAM. ***

The only MiMo-V2.6-Pro GGUF that exists, kernelpool/MiMo-V2.6-Pro-RL-MXFP4-GGUF, totals 557,146,510,560 B = 518.88 GiB against this box's 503 GiB. Short by ~15.9 GiB. It cannot be loaded at all, not "tight" as context-and-speed-per-model said. The architecture blocker is gone — llama.cpp PR #29257 merged Sep 22 2026, MiMo-V2.6 Pro and Flash convert and load with vision and no runtime changes — but RAM is now the blocker instead, and no smaller Pro quant has been published. Downloading 573.5 GB of safetensors plus a multi-hour conversion buys a model that will not load. OPTIONS, decide before leaving: (a) skip MiMo entirely and reclaim 573.5 GB and ~3 hours of the trip; (b) take it anyway only if the 1 TB RAM path is going ahead (see system-performance-levers — that path now looks better than recorded, since 64 GB LRDIMMs hold 2133 at 2DPC); (c) take MiMo-V2.6-Flash instead, which is a different and much smaller model; (d) take the 9B distill for a taste of the family at GPU scale.

### THE REST OF THE MANIFEST SURVIVED AUDIT INTACT

All 21 download-critical claims in model-pull-and-flags verified exact against the HF API — every repo, folder, filename and byte count. Two previously-UNVERIFIED items are now confirmed: Jackrong Q3_K_M = 13,500,736,832 B and GLM-5.3-Flash UD-Q4_K_XL = 199,707,321,347 B (199.7 GB, 6 shards). Hy4 IQ1_M = 235,351,974,336 B exact; its required patch 0001-hyv4-architecture.patch = 92,189 B, targeting llama.cpp commit 0cea36222.

### *** RECONSIDER THE Hy4 "DO NOT PULL" EXCLUSIONS — THEY REST ON UNSOURCED REASONING ***

model-pull-and-flags rules out Hy4 Q4_K_M (435.2 GiB) and STQ1_0 (213.7 GiB). The audit found both exclusions unsupported: AngelSlim publishes no throughput figure for Q4_K_M and explicitly recommends it as the default ("Use this unless you are memory-constrained"), and the README never says STQ1_0 is CUDA-only — that was inferred from a patch filename. STQ1_0 also carries the only published Hy4 benchmark anywhere: pp512 204.56 t/s, tg128 20.47 t/s. Since this file's governing rule is "the scarce resource is the TRIP, not the disk" and ~2.1 TB is spare, take them at the fast house and decide on the box. An exclusion made on arithmetic rather than measurement is not worth a second trip.

### GLM-5.3 IS A BETTER BUY THAN RECORDED

The "GLM-5.3 context is 19K-813K, unknown" caveat is largely resolved: llama.cpp master allocates no V cache for MLA models and caches K over kv_lora_rank + qk_rope_head_dim, i.e. ~87.75 KiB/token → ~813,000 tokens at 68 GiB headroom. Plan GLM-5.3 as a genuine long-context model. Also worth knowing before the trip: Unsloth ships GLM-5.3 UD-IQ1_S at 216.7 GB = 201.8 GiB. That quant fits one socket (201.8 < 251) and is NUMA-mirrorable (403.6 < 503) — the flat "NO QUANT OF GLM-5.3 FULL IS BOTH MIRRORABLE AND GOOD" conclusion in cpu-moe-speed-levers silently assumed Q4_K_XL. Quality at IQ1_S is a real cost and unmeasured, but the door is not closed the way that file says. Consider adding IQ1_S (216.7 GB) alongside Q4_K_XL so the mirroring experiment is possible without a second trip.

### *** SAME DAY, REVERSED AGAIN: MiMo IS BACK ON THE LIST — BUT PULL THE GGUF, NOT THE SOURCE. ***

The "drop item 7" entry above is superseded. A Pro GGUF now exists and MiMo is runnable on this box with -ot expert offload. Full working in mimo-v2.6-feasibility. SWAP THE ITEM: | OLD item 7 | NEW item 7 | | XiaomiMiMo/MiMo-V2.6-Pro-RL source, 573.5 GB, + a multi-hour local conversion needing ~1,032 GiB of concurrent disk | kernelpool/MiMo-V2.6-Pro-RL-MXFP4-GGUF, 557.1 GB, directly runnable | This is strictly better: 16 GB smaller, no conversion, no 1 TB disk requirement, and the vision/audio towers are already stripped. PULL EXACTLY THESE THREE FILES:

- MiMo-V2.6-Pro-RL-MXFP4.gguf.part1 — 480,000,000,000 B
- MiMo-V2.6-Pro-RL-MXFP4.gguf.part2 — 77,146,510,560 B
- MiMo-V2.6-Pro-RL-DFlash-Q8_0.gguf — 2,941,587,648 B (the speculative-decoding draft — do NOT skip it, it is ~1.3-1.6x on a CPU MoE and kernelpool only disables it because their own deployment is tensor-parallel) *** THEY ARE RAW SPLITS, NOT gguf-split SHARDS. *** Join with cat ...part2 >> ...part1 && mv ...part1 ...gguf. Appending into part1 caps the transient cost at part2's size: 634 GB peak. Do the join on the 990 PRO (815 GB free), not the 4TB HDD, and do it at the fast house so a bad byte is a re-fetch rather than a second trip. Checksum both parts against the HF API sha256 before leaving, per this file's existing verify rule — a corrupt 480 GB part discovered at home is unrecoverable on a 4.1 MB/s line. REVISED TOTAL: unchanged in practice (557.1 GB in place of 573.5 GB, ~16 GB less).

## *** Sep 23 2026 — BIGGEST PRE-DOWNLOAD FINDING YET: ISTA-DASLab GSQ-RCO QUANTS. DOWNLOAD THESE INSTEAD OF / ALONGSIDE THE UNSLOTH UD QUANTS. ***

Jack asked for exhaustive pre-download research before committing the trip. This is the answer, and it changes item 1. WHO: ISTA-DASLab = IST Austria Distributed Algorithms and Systems Lab — the group behind GPTQ, QuIP, AQLM and HIGGS. This is a serious quantization research lab, not a community repacker, and they publish per-benchmark recovery plots with each release. GSQ = Gumbel-Softmax post-training scalar quantization (learns per-coordinate grid assignments and per-group scales). RCO = Riemannian Constrained Optimization, which assigns a quant type per TENSOR against a total size budget. Code: github.com/IST-DASLab/GSQ. *** Runs unmodified on mainline llama.cpp — no special build. ***

### *** Qwen3.8-Flash-Next: GSQ-RCO IQ3_XXS IS ~65% FASTER THAN UD-Q4_K_XL FOR A CLAIMED 99.4% OF QUALITY ***

ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF, verified live from the HF API (2-part splits, -00001-of-00002 naming, so llama.cpp follows them automatically — these are proper gguf-split shards, NOT raw cat parts like MiMo's): | Quant | bytes | GB | GiB | bpw | GB/token @6B active | est. t/s @36.6 GB/s | | IQ3_XXS | 47,039,860,096 + 28,800,138,432 = 75,839,998,528 | 75.84 | 70.63 | 3.00 | 2.25 | ~16.3 | | IQ2_XS | 39,225,954,592 + 28,800,138,432 = 68,026,093,024 | 68.03 | 63.35 | 2.50 | 1.875 | ~19.5 | | Q2_0 | 37,623,740,192 + 28,800,138,432 = 66,423,878,624 | 66.42 | 61.86 | 2.40 | 1.80 | ~20.3 | | (for comparison) unsloth UD-Q4_K_XL | 111,334,654,784 | 111.3 | 103.69 | 4.95 | 3.71 | ~9.9 | QUALITY CLAIM [VENDOR, but from a research lab with published plots]: IQ3_XXS "matches the base model exactly on AIME25 (100.00)" and reaches 99.4% of baseline task average at 4.7x smaller than BF16. The repo ships per-benchmark recovery plots (aime25, gpqa_diamond, lcb, ppl on c4/fineweb-edu/wikitext2, task_avg, zero-shot task_avg) — verify against those plots before trusting the headline. WHY THIS MATTERS SO MUCH HERE: decode is bytes/token bound, so 3.00 bpw vs 4.95 bpw is a straight ~65% decode gain, and 70.63 GiB is so far inside one socket that NUMA mirroring (~1.5x) is trivial — stacking to roughly 24 t/s before MTP. It also saves 35.5 GB of download. *** RECOMMENDATION: take IQ3_XXS (75.84 GB) AND keep UD-Q4_K_XL (111.3 GB) so they can be A/B'd on the box. 187 GB total, still well inside the drive. Deciding later costs nothing; deciding wrong now costs a trip. *** OPEN QUESTION TO SETTLE ON THE BOX: does the unsloth MTP/mtp-...-shared-Q8_0.gguf draft pair with an ISTA-DASLab main model? Precedent says likely yes — unsloth's MTP head for the 27B pairs fine with ggml-org's main weights (same base model, same vocab 248320), per jarvis-speed-tuning. Same logic applies. Grab the MTP folder regardless; it is ~4 GB and it is the difference between ~16 and ~30+ t/s. NOTE ON THE SPLITS: part 2 is byte-identical in size (28,800,138,432) across all three quants — that is the fixed-precision shared component (embeddings / the n-gram table). Only part 1 shrinks with the quant. Does not change the totals above, but explains why the bpw gap is smaller than the file-size gap suggests.

### ALSO FOUND — GSQ-RCO FOR THE 27B, AND WHY IT DOES NOT REPLACE ITEM 3

ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF: IQ2_XS 8,422,841,472 / IQ2_S 9,259,510,912 / IQ3_XXS 10,094,357,632 (9.40 GiB), plus mmproj-BF16 931,146,528. *** CRITICAL: NONE of these carry MTP. *** So they do NOT replace item 3 (RentedNoodle/...-GSQ-RCO-IQ3_XXS-Uncensored-MTP, 10.4 GB), which is the same GSQ-RCO quant family with the MTP head inside the file — and MTP is worth ~2.5x on this box. Keep RentedNoodle. The ISTA-DASLab 27B is the better-pedigree quant but loses far more to missing MTP than it gains in quality. They may however replace item 4 (Jackrong/Qwen3.8-27B-MTP-GGUF Q3_K_M, 13,500,736,832 B) if that file's MTP turns out to be absent or broken — check item 4's tensor list on arrival before relying on it.

### WHAT GSQ-RCO DOES NOT COVER — these stay exactly as planned

Checked ISTA-DASLab's full repo list and searched: no GSQ-RCO for GLM-5.3 full, Hy4-preview, or MiMo-V2.6. GLM-5.3-Flash has community GSQ-RCO repos (taurusduan/, pfeifferj/) but Flash is archive-only on this list anyway.

### ADD: GLM-5.3 UD-IQ1_S SO THE MIRRORING EXPERIMENT IS POSSIBLE

Per the Sep 23 audit, unsloth ships GLM-5.3 UD-IQ1_S at 216.7 GB = 201.8 GiB, which fits one socket (201.8 < 251) and mirrors (403.6 < 503) — worth a measured 1.47-1.63x. Q4_K_XL at 435 GiB can do neither. Quality at IQ1_S is a real and unmeasured cost, but without this file on the drive the mirroring experiment cannot be run at all, and it is +216.7 GB against ~1.9 TB spare.

## *** Sep 23 2026 — 27B VARIANT CLEANUP. Jack asked why there were so many and chose to keep ONE. ***

Four 27B files had accumulated on the list at different times without ever being compared. Against the hard VRAM limit (15.77 GiB per card, 31.5 GiB total): | file | GiB | fits ONE card? | uncensored? | MTP? | | ggml-org Q4_K_M (already on the box) | 17.66 | no | no | yes, separate head | | RentedNoodle GSQ-RCO IQ3_XXS-Uncensored-MTP | 9.7 | yes, comfortably | yes | yes, in-file | | Jackrong Q3_K_M-MTP | 12.6 | yes, tight | no | yes | | HauhauCS Aggressive Q5_K_P | 18.8 | no, needs both | yes | yes, FastMTP sidecar | Jackrong and RentedNoodle were doing the SAME job (a small 27B+MTP that fits one card, to free the second V100); Jackrong is merely censored and 3 GiB larger. RentedNoodle and HauhauCS are NOT redundant — they sit on opposite sides of the single-card boundary.

### *** DECISION: keep HauhauCS Q5_K_P ONLY. Drop items 3 (RentedNoodle) and 4 (Jackrong). ***

Jack chose the "swap in when needed" layout: production 27B runs normally; to use the uncensored model, stop llama-server.service, run HauhauCS across both cards, stop it, restart production. ~3 minutes each way (the 120 s draft load dominates), exactly the procedure used for the sm70-attn fork tests Sep 23. Saves 23.9 GB. Revised total ≈ 1,906 GB. WHY BOTH CANNOT RUN AT ONCE, the arithmetic behind the choice: HauhauCS 18.8 GiB + production 17.66 GiB = 36.5 GiB against 31.5 GiB of VRAM. One must stop for the other to start.

### *** CONSEQUENCE FLAGGED TO JACK, AND IT CONTRADICTS AN EARLIER ENTRY IN THIS FILE ***

Dropping both small 27Bs KILLS the GPU re-layout in orchestrator-slot-plan — that plan's premise is a small 27B+MTP on ONE card so the second V100 comes free for another slot. Nothing left on the list is small enough to do that, so both cards stay committed to whichever 27B is loaded. This directly reverses this file's own earlier line promoting RentedNoodle "from maybe to certain" as "the ONLY item on the whole list that meets Jack's stated ~50 t/s interactive bar." That promotion is now overridden by Jack's explicit choice. The reasoning that makes it defensible: he already HAS a 69 t/s interactive model (production, measured Sep 23), so the freed-card slot was speculative rather than load-bearing. IF THE RE-LAYOUT IS EVER REVIVED, RentedNoodle (10.4 GB) is the file to add back — small, uncensored, MTP in-file, same GSQ-RCO family. Do not substitute ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF: better quant pedigree but no MTP, and MTP is worth ~2.5x on this box.

## *** Sep 23 2026 — QUANT PICKS SETTLED AGAINST REAL PUBLISHED TABLES. ONE EARLIER RECOMMENDATION RETRACTED. Full tables in quant-quality-tables. ***

### *** RETRACTED: DO NOT BUY THE GLM-5.3 UD-IQ1_S MIRRORING IDEA. ***

I recommended adding UD-IQ1_S (216.7 GB) so NUMA mirroring would be possible. Checked against glm-5.3-quant-quality's Unsloth table, that is a bad trade under Jack's no-quality-loss constraint: | | top-1 accuracy | mean KLD | perplexity | | UD-IQ1_S | 72.56% | 0.688 | 4.613 | | UD-Q4_K_XL | 94.29% | 0.037 | 2.701 | Mirroring buys ~1.5-1.6x speed on a model that is 22 points worse on top-1 token accuracy and 18x worse on KLD. That is not "the same model, faster" — it is a materially worse model. Drop UD-IQ1_S. Saves 216.7 GB. The existing conclusion stands: no quant of GLM-5.3 full is both mirrorable and good. Take UD-Q4_K_XL (467.3 GB) only.

### FLASH-NEXT: TAKE THREE QUANTS, AND THE REASON IS PREFILL, NOT SIZE

ISTA-DASLab's own llama.cpp measurements (55 prompts): Q2_0 gets 367.49 t/s prefill vs IQ2_XS's 108.19 — 3.4x — at essentially the same file size. The gap is dequantisation cost, and i-quants are compute-hungry exactly where Jack is weakest (AVX2, no AVX-512). Since cpu-moe-hardware-anchors shows prefill is the binding constraint (16-44 t/s on comparable hardware), this may matter more than the quality gap. | take | GB | why | | GSQ-RCO IQ3_XXS | 75.8 | the quality pick: 99.4% of BF16 task avg, AIME25 exact match. But it is an i-quant, so prefill is the open question | | GSQ-RCO Q2_0 | 66.4 | the speed pick: 3.4x prefill, 1.9x lower latency. Costs ~3.5 points of task avg (89.07 vs 93.12), mostly on code (LCB −6.3) | | unsloth UD-Q4_K_XL | 111.3 | insurance. K-quant (fast dequant, no i-quant penalty) and the quant the unsloth MTP drafts are known to pair with. Keep until the GSQ-RCO + MTP pairing is proven on the box | 253.5 GB for all three. The A/B cannot be done from published numbers — no IQ3-vs-Q-type comparison at 3 bpw exists anywhere — so it has to be measured on Jack's hardware, which means all three have to come home.

### 27B: A TASK-LOSSLESS ONE-CARD OPTION EXISTS, BUT IT HAS NO MTP

ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF IQ3_S, 3.50 bpw, 11.8 GB = 11.0 GiB is task-lossless: AIME25 and LCB v6 match BF16 exactly, GPQA-D −0.51, wikitext ppl 7.07 vs 7.05. It fits ONE V100 with ~4.7 GiB spare for KV. Not added, because it has no MTP — a lossless one-card 27B at ~29 t/s loses to the current MTP production config at ~69 t/s (measured). Add it only if the freed-GPU re-layout is revived, and note it would then be the quality-correct choice over RentedNoodle's IQ3_XXS.

### REVISED TOTAL

Was ~1,906 GB. −216.7 (drop GLM-5.3 IQ1_S) +66.4 (add Flash-Next Q2_0) = ~1,756 GB. Against 3,726 GB, ~1.97 TB spare, roughly 9.8 hours at 50 MB/s.

### CAUTION CARRIED FORWARD FROM THE TABLES

Several GSQ-RCO rows report above 100% recovery (Q2_0 at 101.4%, 27B IQ2_S at 101.8%). A quantised model cannot beat its own baseline, so the zero-shot suite is noisier than the differences it is being used to resolve. Judge on AIME25 / GPQA-D / LCB / perplexity, not on "recovery %". And do not transfer the GSQ-RCO result to GLM-5.3 — different method, much steeper curve, and no GSQ-RCO exists for it.

## *** Sep 23 2026 — HauhauCS UNCENSORED 27B: THE PATCH IS REQUIRED, NOT OPTIONAL. AND THE QUALITY CLAIMS HAVE NO EVIDENCE. [README read live] ***

RESOLVES the open question flagged earlier in this file. The FastMTP draft will not load without HauhauCS-FastMTP-llama.cpp.patch — without it you get a vocabulary mismatch: expected 5120, 248320, got 5120, 32768. That is exactly the d2t draft-vocab-trimming path the patch implements, confirming the suspicion recorded earlier. The patch is mandatory for the draft; the main Q5_K_P model presumably loads without it, but the MTP speedup does not. *** IT ALSO PINS AN EXACT llama.cpp COMMIT: 4df29be4f4c3673f428170fda944a5b19f743bb8. *** That is neither Jack's b11089 nor the fishlikeX/sm70-attn fork nor Hy4's 0cea36222. Expect a rebase, and note this means a THIRD separate llama.cpp build if the uncensored model is to have working MTP. Budget for that before assuming the 3.02x FastMTP figure applies. THE VENDOR CLAIMS HAVE NO SUPPORTING DATA — verified by reading the README:

- "K_P quants bump quality up by one or two quant levels at only 5-15% more size" — no perplexity, no benchmarks, no KLD, nothing. Contrast with quant-quality-tables, where GSQ-RCO and Unsloth both publish full tables. Treat K_P as an unmeasured custom scheme.
- "0/465 Refusals" — no methodology, no prompt set, no definition of refusal.
- FastMTP "up to 3.02x document TG / 1.93x reasoning TG" — measured on an RTX PRO 6000 Blackwell 96GB, reaching 1613.81 PP t/s and 131.81 TG t/s. Blackwell, not Volta. These numbers will not transfer to a V100, and Jack's own measured MTP gain on this box is ~2.5x, so the incremental benefit of FastMTP over a standard MTP head may be small. NOT A REASON TO DROP IT — Jack chose it deliberately and the uncensored slot has no better-documented option (checked ~27 uncensored Qwen3.8-27B repos; none publish quality tables). But download IQ4_XS (15.71 GB) alongside Q5_K_P: it is a STANDARD quant with known behaviour rather than the undocumented K_P scheme, and at 14.63 GiB it fits a single V100 where Q5_K_P's 18.8 GiB does not. That is a real fallback for both quality-verification and single-card use, for 15.7 GB.

## *** Sep 23 2026 — DROP Hy4-preview. FULL REASONING IN quant-quality-tables. ***

Tencent DID publish quality data (98-99% retention at 1.78 bpw avg) — but only for MIX-STQ1_0, and llama.cpp PR #22836 gives STQ1_0 an ARM NEON CPU kernel, not AVX2. On x86 it is CUDA-only, and 213.66 GiB will not fit 31.5 GiB of VRAM. The quant with the data cannot run; the quant that runs (UD-IQ1_M, 2.44 bpw i-quant) has no data. Plus it is the slowest model on the list, scores below GLM-5.3, and needs a patch rebase. Saves 235.4 GB.

## RUNNING TOTAL AFTER TODAY'S CUTS

Started ~1,930 GB. −216.7 (GLM-5.3 IQ1_S, quality-retracted) +66.4 (Flash-Next Q2_0) −235.4 (Hy4) +15.7 (HauhauCS IQ4_XS) = ~1,560 GB, or ~1,360 GB if GLM-5.3-Flash (199.7 GB, architecture unmerged everywhere) is also dropped. At 50 MB/s that is 8.7 h, or 7.6 h without GLM-5.3-Flash. Against 3,726 GB the drive is now barely half full, so nothing on this list is constrained by disk — every cut above was made on quality or runnability grounds, not space.

## *** Sep 23 2026 — GLM-5.3-FLASH IS RUNNABLE, WITH MTP, VIA AN OFFICIAL UNSLOTH BUILD. PROMOTE IT FROM "ARCHIVE ONLY" TO A REAL SLOT. ***

Jack asked to research whether he can run GLM-5.3-Flash. He can. This overturns the "no lane / architecture unmerged everywhere / archive only" verdict in model-tier-ceiling and earlier in this file.

### THE BUILD PATH IS DOCUMENTED AND MAINTAINED BY UNSLOTH [SOURCE: unsloth.ai/docs/models/glm-5.3-flash]

bash

```bash
git clone --branch glm5next/upstream https://github.com/unslothai/llama.cpp
```

cmake llama.cpp -B llama.cpp/build -DBUILD_SHARED_LIBS=OFF -DGGML_CUDA=ON

```bash
cmake --build llama.cpp/build --config Release -j --clean-first \
  --target llama-cli llama-mtmd-cli llama-server llama-gguf-split
```

Their own words: "We need to use our specific llama.cpp PR" (unslothai/llama.cpp PR #61). This is a maintained vendor fork, not the abandoned community PR #27773 this memory was tracking. The mainline PRs (#27754, #27752, #27773) remain stalled and are no longer the relevant path. *** AND IT HAS MTP: "faster decoding path plus bonus MTP support, enabling up to 3.3x faster inference at long context lengths." *** About 1.5-1.6x at 4K, rising to 3.3x long. Unsloth's own caveat: stop at n=2 — more draft tokens make it SLOWER. (Consistent with Jack's own n_max sweep on the 27B, where past 5 was a monotonic loss. Over-drafting is the recurring trap on this box.) Run flags from their docs: --temp 1.0 --top-p 0.95 --chat-template-kwargs '{"reasoning_effort":"max"}'. Note max, not xhigh, for this model family.

### *** THE ARITHMETIC, AND IT IS BETTER THAN GLM-5.3 FULL BY A WIDE MARGIN ***

| | GLM-5.3 full UD-Q4_K_XL | GLM-5.3-Flash UD-Q4_K_XL | | download | 467.3 GB | 199.7 GB | | resident | 435.2 GiB | 186.0 GiB | | active params | 40B | 18B | | GB/token | 24.8 | 11.23 | | raw decode @36.6 GB/s | 1.48 t/s | 3.26 t/s | | fits ONE socket (251 GiB)? | NO — forced cross-QPI | YES, 65 GiB spare | | NUMA mirrorable (2x < 503)? | NO (870 needed) | YES (372) | | + mirroring (~1.5-1.6x) | n/a | ~5.0-5.2 t/s | | + MTP | none published | ~7.5-8 t/s at short ctx, more at long | | top-1 accuracy at this quant | 94.29% | 92.22% | | AA index | 45 | 42 | *** GLM-5.3-Flash is roughly 3-5x faster than GLM-5.3 full, for less than half the download, at 92.22% vs 94.29% top-1 — both near-lossless rungs — and 3 index points lower. *** It is the only big model on the list where mirroring, MTP and single-socket residency all stack. PRACTICAL VERDICT: Flash is the better AGENTIC model; full is the better ONE-HARD-QUESTION model. Take both; they are not competitors.

### REAL USER NUMBERS (ik_llama PR #2376, a different build but the same architecture)

3x RTX 3090 + DDR4: ~68 ms/token = 14.7 t/s decode. 1x 3090 + Epyc Milan: 6.1 t/s decode, 95.8 t/s prompt. 2x3090+A4000+192GB DDR5: ~100 t/s prompt, 8 t/s decode at 16K. All GPU-heavy, so Jack's CPU-resident figure will be lower — the 5-8 t/s projection above is consistent with the weakest of these.

### CAVEATS THAT MUST BE TESTED, NOT ASSUMED

- PROMPT-CACHE RISK IS HIGH. KDA hybrid linear attention is exactly the recurrent class flagged in cpu-moe-speed-levers as breaking incremental KV reuse. If it breaks, every turn reprocesses the whole prefix and the speed win evaporates on multi-turn work. Test with the "forcing full prompt re-processing" log line (prints at default verbosity — -lv 4 is NOT needed).
- LONG-CONTEXT DEGRADATION BUG, reported against mainline PR #27754: output collapses to repeated tokens, failing ~78-88K in at -c 262144 and ~60-71K in at -c 524288. Unknown whether Unsloth's branch carries the fix. Do not trust past ~60K until tested.
- OOM at ~32K prompt reported on ik_llama #2376. Different build, but worth watching.
- This is a FOURTH separate llama.cpp build (alongside b11089, fishlikeX/sm70-attn, and HauhauCS's pinned commit). Budget the build time.

### MANIFEST CHANGE

Keep GLM-5.3-Flash UD-Q4_K_XL (199.7 GB), promoted from "archive only" to a real slot — and take ONLY Q4_K_XL, since quant-quality-tables shows everything below it drops to 81.63% top-1 or worse. Also grab incoai/GLM-5.3-Flash-DFlash2 if it is a usable draft (unverified), and the GLM-5.3-Flash imatrix (512.7 MB) already on the list. Total stands at ~1,560 GB — the earlier "~1,360 if Flash is dropped" option is withdrawn.

## *** Sep 23 2026 — FINAL "DID I MISS A BETTER MODEL" SWEEP, RUN BEFORE COMMITTING THE TRIP. ANSWER: NO. ***

Jack: "I don't want to download a big model, only to find out there was a better one." Re-checked the Artificial Analysis large open-weights board live (index v4.3.2, unchanged from the Sep 22 survey) and verified runnability for every entry ABOVE the models on the list.

### THE COMPLETE PICTURE, CAPABILITY vs WHAT IS ACTUALLY RUNNABLE

| rank | model | index | total/active | best runnable quant | top-1 at that quant | est. t/s | status | | 1 | MiMo-V2.6-Pro | 46 | 1.0T/42B | MXFP4 518.88 GiB (only option) | unpublished | ~2-3 | RUNNABLE with -ot offload, ~489 GiB vs ~497 available. Tight | | 2 | GLM-5.3 (max) | 45 | 753B/40B | UD-Q4_K_XL 435.2 GiB | 94.29% | ~1.5-4 | RUNNABLE | | 3 | Kimi K3 (max) | 44 | 2.8T/104B | — | — | — | *** BLOCKED, see below *** | | 4 | GLM-5.3-Flash | 42 | 320B/18B | UD-Q4_K_XL 186.0 GiB | 92.22% | ~5-8 | RUNNABLE, mirrorable, MTP | | 5 | Qwen3.8 2.4T A95B | 40 | 2.4T/95B | — | — | — | *** NO GGUF EXISTS AT ALL *** (only BF16/FP8/NVFP4/INT8 safetensors). And at 95B active it would be ~16x slower than Flash-Next for the SAME index 40 — strictly dominated even in principle | | 6 | Qwen3.8-Flash-Next | 40 | 180B/6B | GSQ-RCO IQ3_XXS 70.6 GiB | 99.4% task avg | ~16-24 | RUNNABLE, the speed champion | | 7 | DeepSeek V4.1 Flash | 39 | 552B/16B | — | — | — | convert-only draft PR #28696; ik PR #2455 draft; 3 incompatible GGUF variants in circulation | | 8 | DeepSeek V4 Pro | 36 | 1.6T/49B | — | — | — | community fork only (cchuter/llama.cpp feat/v4-port-cuda) | Below rank 8 (Kimi K3 low 34, Motif 3 34, K2 Horizon 375B 31, MiniMax-M3 29) nothing outranks what is already on the list; K2 Horizon 375B is explicitly refused upstream (llama.cpp discussion #28308).

### *** KIMI K3 IS OUT, AND THE SIZE IS THE LESSER REASON. [SOURCE: unsloth.ai/docs/models/kimi-k3] ***

| Quant | Size GB | RAM needed GB | Mean KLD | PPL | Top-1 | | UD-IQ1_S | 594.0 | 610 | 0.5645 | 2.5789 | 78.875% | | UD-IQ1_M | 648.9 | 665 | 0.4789 | 2.3639 | 81.219% | | UD-IQ2_XXS | 711.1 | 726 | 0.3784 | 2.1266 | 84.127% | | UD-Q2_K_XL | 861.3 | 880 | 0.1779 | 1.7359 | 90.390% | SIZE: the smallest quant needs 610 GB of RAM against Jack's 540 GB (503 GiB). Even with ~30 GiB of -ot GPU offload it lands ~523 GiB, still over. Confirms the existing "594 GB, ruled out" note — and the UD-TQ1_0/UD-Q1_0 filenames visible in the repo listing are NOT in Unsloth's docs and carry no published quality numbers; ternary types applied to a non-ternary-trained model destroy it anyway. *** THE DECISIVE REASON, AND THE GENERAL LESSON: FULL-PRECISION INDEX IS NOT THE INDEX YOU GET. *** Kimi K3 scores 44 at BF16, but the only quant that would even approach fitting runs at 78.9% top-1. GLM-5.3 scores 45 and runs at 94.29% top-1. GLM-5.3 at Q4 strictly dominates Kimi K3 at IQ1_S on both axes. The quantization gap (15 points of top-1) swamps the 1-point index gap several times over. KEEP THIS RULE: rank models by (index at the quant that fits), never by (index at BF16). It is the same error that made Hy4 look attractive, and it is why the 2.8T and 2.4T models are not worth wanting.

### CONCLUSION: THE LIST IS THE RIGHT LIST

Every model scoring above GLM-5.3-Flash that Jack cannot run is blocked for a hard, verified reason — RAM (Kimi K3), no GGUF (Qwen3.8 2.4T), or no runtime (both DeepSeek V4 lines). None of them would be better in practice even if unblocked, because each would land at a quant or a speed that puts it behind what is already on the list. Atria Dawn Preview is also settled and stays off (see atria-dawn-preview): config-for-config identical to GLM-5.3, therefore the same ~40B active and the same ~1.6 t/s, wins tool use by 2.9 BFCL points, LOSES on coding (SWE-bench Pro 59.6 vs 61.4), and has no GGUF — it would need a self-conversion to land beside a model already on the list. No regret risk identified. Download with confidence.

## *** Sep 23 2026 16:10Z — THE FAST-HOUSE PULL IS RUNNING. REAL MEASURED THROUGHPUT: ~30 MB/s, NOT 50. [MEASURED] ***

Setup that worked: drive is D:\models on desktop-9ii55td (Windows x64, NOT the ARM64 "seaturtle" laptop the earlier plan assumed). Claude has no device_bash on this machine and computer-use grants terminals click-only (no typing), so the working pattern was: *** Claude writes a script to the connected folder with device_commit_files, Jack runs one PowerShell line. *** Reuse this pattern; do not plan around typing into his terminal. Scripts live on the drive: D:\models\RUN.ps1 (bootstraps a venv + huggingface_hub[hf_xet], requires D:\models\hf_token.txt) and D:\models\pull.py (11-item manifest, verifies every repo/pattern against the HF API before downloading, sequential in priority order, marker files so a re-run skips finished items, 60-second size sampler that alerts on a SHRINKING total — the xet failure from glm-5.3-download). MEASURED PER-ITEM RATES: item 2 (HauhauCS Q5_K_P + FastMTP, 21.12 GB) 12.4 min = 28.5 MB/s; item 3 (IQ4_XS, 15.71 GB) 7.4 min = 35.2 MB/s. Xet "reconstruction" bursts show 106-171 MB/s but those are local dedup, not wire speed. Plan on ~30 MB/s, i.e. ~1.7x slower than the 50 MB/s every earlier estimate in this file assumed. CONSEQUENCE: the ~1,550 GB list is ~14 hours, not ~8.5. Every ETA above this line is optimistic by that factor. SIZE CORRECTION: item 4 unsloth/Qwen3.8-Flash-Next-GGUF MTP/* + imatrix* is 25.20 GB, not the ~4.6 GB this file estimated — the MTP/ folder holds all six variants (BF16 through shared-Q8_0), not just shared-Q8_0. Harmless (they are wanted anyway) but it means the folder-level estimates elsewhere in this file undercount.

### WHAT IS ON THE DRIVE, AND THE 10 PM PLAN (Sep 23 2026)

Jack left the pull running unattended and returns to that house by 10 PM Central. At ~33 MB/s the remaining items 7-11 (IQ3_XXS, Flash-Next Q4, GLM-5.3-Flash, GLM-5.3 full, MiMo) are ~11 h, so ETA 11 PM - midnight — he arrives near the end, not after it. Scripts staged on the drive for him, all inert until run: pull_one.py (one-off repo+pattern puller, e.g. Flash-Next Q8_0), verify.py + VERIFY.ps1 (checksums every file against HF's published sha256, --size-only for an instant truncation check, caches passes in _logs/verified.json so an interrupted run resumes), and README-FIRST.txt on the drive itself. Q8_0 deferred, not refused — Jack asked whether manifest edits apply to a running job. *** THEY DO NOT: pull.py reads ITEMS once at startup, so nothing can be added or dropped mid-run. *** Editing the file only affects the next run. Recorded because it will come up again. FULL sha256 OF ~1.5 TB ON A USB HDD IS ~3 HOURS and contends with any download still running on the same spindle. --size-only is seconds and catches truncation, the common failure, but not silent corruption. DECISION CHANGED FROM THIS FILE'S EARLIER RULE: do NOT join MiMo's two raw parts at the fast house. Checksumming the parts there already achieves the "a bad byte is a refetch, not a second trip" goal, and the join needs no network — so joining at home saves ~1.3 h of fast-house time. Join with cmd /c "type ...part2 >> ...part1" then rename; copy /b is unreliable at this size.
