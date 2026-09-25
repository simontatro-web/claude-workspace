# GLM-5.3 (UD-Q4_K_XL): speed research and runbook

For Simon. Written 2026-09-25 (evening, Central time). Labels: MEASURED (on jarvis-1, with date), SOURCE (link), ESTIMATE (arithmetic shown), VERIFY (not checked yet; a read-only command is in section E).
Role assumed here: the strongest model on the box (Artificial Analysis index 45 vs Flash-Next 40, per the wiki), used for background jobs, not chat: it answers at about 1 token per second. It needs ~430 GiB of RAM, so it runs only when no other big model is loaded. Steps that stop Jarvis or change the box are marked SIMON ONLY; the rest run beside Jarvis on the CPU and Jarvis may run them.
Inputs read: docs/benchmarks/glm-5.3.md and docs/glm-5.3-test-plan.md (branch claude/new-session-uyo1y3 at 7be739a), the wiki pages glm-5.3-quant-quality, cpu-moe-speed-levers, big-model-decode-prefill, system-performance-levers, and the llama.cpp source at the production commit f4e276a20 and ik_llama.cpp at 1aaf7105.
Scripts: this runbook uses `cpu_test.py` and `gguf_bytes.py`, delivered by step FN-1 in [qwen3.8-flash-next.md](qwen3.8-flash-next.md). If FN-1 has not been done, do it first (it only writes files under ~/speed).

## A. Current state

**Model** (MEASURED 2026-09-25): unsloth GLM-5.3 UD-Q4_K_XL, 11 shards, 467.3 GB (435 GiB), sha256-verified, at `/home/simon/models/GLM-5.3/UD-Q4_K_XL/`. 753.9B parameters, 40B active per token, 78 layers, MLA attention (kv_lora_rank 512), DSA "lightning indexer" (sparse attention over the top-k keys), and one MTP layer: the NextN head `blk.78.nextn.*` is in shard 11 (MEASURED by the benchmark session).
**Quality of this quant** (SOURCE: Unsloth's table, wiki glm-5.3-quant-quality): top-1 94.29% and mean KLD 0.037 vs full precision. The next size down, UD-IQ3_XXS, is 84.15% / 0.273.
**Resident size** (MEASURED): CPU model buffer 184,022 MiB + CPU_REPACK 255,744 MiB = ~430 GiB, weights repacked to q4_K_8x8 at load.

**Measured speed** (all MEASURED 2026-09-25 night 1, stock llama.cpp f4e276a20, llama-bench, CPU only, `-lm dio`):

| Setup | Decode t/s | Prefill t/s | Notes |
|---|---|---|---|
| Beside Jarvis (`numactl --preferred=1`), 36 threads, empty context | 0.9-1.1 | 9.9 (pp512), 7.6 (pp4096) | decode varies run to run; keep a control in every test |
| Interleaved, Jarvis stopped | **1.48** | 10.1 / 7.6 | best decode so far |
| Depth 0 / 4K / 16K, beside Jarvis | 1.11 / 0.93 / 0.74 | - | -33% by 16K |
| Depth 16K, interleaved, Jarvis stopped | 1.00 | 2.51 (pp512), 2.83 (pp4096) | prefill falls ~4x by 16K |
| Threads 18 / 32 / 36 (beside) | 0.96 / 0.86 / 0.89 | 5.71 / 9.53 / 9.87 | decode flat, prefill wants 36; 72 threads +1% |
| Flash attention on vs off at 8K depth | 0.84 vs 0.72 | 3.99 vs 4.71 | FA: +17% decode, -15% prefill |
| ubatch 512 / 1024 / 2048 / 4096 (pp4096) | - | 7.45 / 7.55 / 7.63 / 7.33 | flat |
| `--poll` 0 / 50 / 100 | 1.10 / 1.10 / 1.10 | 9.90 / 9.89 / 9.87 | no effect |
| K cache q8_0 with FA on | - | - | "failed to create context" |
| GPU hybrid | - | - | all three jobs failed on test-design errors (`-cmoe` is not a llama-bench flag; `-ncmoe 76`/`74` did not fit the GPUs) |

**Two corrections to earlier notes (accuracy over reassurance)**
1. The benchmark doc and test plan say the DSA sparse indexer is "not implemented" and the model "runs as full MLA attention". The production source says otherwise: `src/models/glm-dsa.cpp` computes the lightning indexer and `ggml_top_k`, and `src/llama-graph.cpp` turns the top-k into an attention mask (`kq_mask_top_k`) (SOURCE, both files at f4e276a20). So stock llama.cpp gives the model's real sparse-attention output, but it still multiplies the query against every key and then masks, so the cost still grows with context. The practical conclusion (prefill gets slow with depth) stands; the reason is "masked, not skipped". The CPU flash-attention kernel skips masked keys one by one, which fits FA-on being faster for decode at 8K (ESTIMATE on the mechanism).
2. The test plan cites ik_llama.cpp discussion #164 for "1.5-1.9x decode, ~1.9x prompt processing vs mainline on comparable AVX2 Xeons". That discussion measured an 8B dense model on a Ryzen 7950X: prompt processing 3.3x, generation +5% ([#164](https://github.com/ikawrakow/ik_llama.cpp/discussions/164)). For a bandwidth-bound MoE decode, expect small decode gains from ik; its big wins are prefill and long context (lever 1 below).

**Limits, with arithmetic**
- Decode: 24.8 GB read per token (benchmark doc; GL-1 re-measures it from the file headers). 1.48 t/s x 24.8 GB = 36.7 GB/s = 62% of the 59.5 GB/s two-socket STREAM Triad (MEASURED Sep 23). That is already a good conversion; at 80% of Triad the ceiling is 47.6 / 24.8 = **~1.9 t/s** without speculation (ESTIMATE). Beside Jarvis with `--preferred=1`: 1.1 x 24.8 = 27 GB/s, so the placement costs ~25%.
- Prefill at depth 0 is compute-bound: 40B active x 2 FLOP = 80 GFLOP per token; 10 t/s = 0.8 TFLOPS effective (ESTIMATE).
- Prefill at depth: 512 tokens take 51 s at depth 0 and ~205 s at 16K (MEASURED rates 10.1 and 2.51 t/s): ~150 s of the 205 s is attention over the 16K earlier tokens. Reading a 32K-token document therefore takes roughly 2.5-3 hours on stock (ESTIMATE: the rate falls from ~10 to ~1.5 t/s along the way). That, not decode, is what limits long-context use.
- KV cache: MLA stores only a 576-value latent per token per layer: (512 + 64) x 2 bytes x 78 layers = ~88 KiB per token at f16 (SOURCE: test plan, from llama-kv-cache.cpp), plus the indexer keys (ESTIMATE 128 x 2 bytes x 78 = ~20 KiB per token). A 32K context is ~3.3 GiB: RAM is not the limit, time is.
- A NUMA mirror is impossible: 2 x 435 GiB > 503 GiB.

## B. Levers, ranked for the background-job role

| # | Lever | Expected gain | Quality risk | Downtime? | Effort | Evidence |
|---|---|---|---|---|---|---|
| 1 | **ik_llama.cpp with real sparse attention** (`--dsa -mla 1`) | ESTIMATE: long-context prefill 3-4x (a 16-32K document in ~30-50 min instead of 2-3 h), decode at 16K+ +30-45%; depth-0 decode about equal | same sparse semantics as stock; near-tie differences possible (check). Without `--dsa`, ik runs dense attention, which is a different model behaviour (perplexity at 2,560 tokens: dense 2.4151 vs sparse 2.4697, [ik #2045](https://github.com/ikawrakow/ik_llama.cpp/pull/2045)); that would need the quality gate | no | GL-5 | SOURCE, CPU-only on a Ryzen 3995WX with GLM-5.2 Q4_K_M: prefill 32.6 / 22.2 / 18.6 t/s at 0 / 32K / 61K with `--dsa -mla 1`, vs 36.8 to 5.19 dense (3.6x at 61K; "`-mla 1` must be used") ([ik #2074](https://github.com/ikawrakow/ik_llama.cpp/pull/2074)); decode 3.89 to 2.78 with DSA vs 3.87 to 1.90 dense ([ik #2068](https://github.com/ikawrakow/ik_llama.cpp/pull/2068)). Caveat from #2045: sparse masking was broken for more than one sequence at once, so use `--parallel 1` (VERIFY whether fixed) |
| 2 | **Save and restore a long context** (`--slot-save-path`) | ESTIMATE: re-reading a 32K document (2-3 h) becomes a ~3.3 GiB file load (seconds) | none if the restored answer matches | no | GL-2 (`slot` test) | server API `POST /slots/0?action=save|restore` (SOURCE: [server-context.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-context.cpp)); the file has no model-identity check, so restore only into the same model and flags (test plan). Whether the DSA indexer cache is in the file: VERIFY (the harness checks the answer is identical after restore). ik saves it ([ik #2146](https://github.com/ikawrakow/ik_llama.cpp/pull/2146), "include DSA indexer state in kv/slot serializer") |
| 3 | **MTP with the built-in head** (`--spec-type draft-mtp`, no draft file) | ESTIMATE 1.3-1.8x decode | output may differ at a near-tie token (check) | no | GL-4 | stock supports it: with `draft-mtp` and no `-md` the server builds the draft context against the target model and loads `blk.78` (SOURCE: common/speculative.cpp and glm-dsa.cpp at f4e276a20). CPU-only GLM-5 on a 3995WX: 5.8 to 10.5 t/s (1.8x) at n_max 2 with an IQ2_KS quant ([ik #1890](https://github.com/ikawrakow/ik_llama.cpp/pull/1890)). MEASURED on this box for Flash-Next: 1.57x. Costs ~5 GB more RAM for the MTP layer |
| 4 | **Interleave beside Jarvis** (instead of `--preferred=1`) | ESTIMATE decode 1.1 to ~1.35-1.45 (+25-35%) | none (same math) | no | GL-3 | MEASURED 1.48 interleaved with Jarvis stopped; for Flash-Next, interleaving beside Jarvis cost Jarvis 3% median, 15% worst probe (MEASURED Sep 25). Node 0 then holds ~218 GiB of GLM next to Jarvis: check free memory first |
| 5 | **GPU hybrid in a Jarvis-off night window** (non-expert tensors on the V100s, experts on CPU, big-batch prefill offload) | ESTIMATE decode +40-70% (CPU then reads only routed experts); prefill with `-ub 4096` 50-120 t/s (all ~420 GB of expert weights cross PCIe 3.0 at ~12 GB/s once per 4,096-token batch, ~35 s) vs 7.6 now; depth barely matters when attention runs on the GPU | none (same math, different kernels: check) | **yes (SIMON ONLY)** | GL-8 | fixes the night-1 test design (`-ncmoe 79` = every MoE layer on CPU). The CUDA backend has the lightning-indexer op (SOURCE: ggml-cuda.cu at f4e276a20). Only useful if Simon accepts Jarvis-off windows for long GLM jobs |
| 6 | **Two jobs at once** (`--parallel 2`) | ESTIMATE +20-50% total throughput, each job slower | none | no | GL-7 | two tokens share the attention and shared-expert reads but usually need different routed experts; stock only (ik `--dsa` needs one sequence) |
| 7 | **First-touch `--numa distribute`** (stock, mmap, `--no-repack`, `-t 36 -tb 36`) | ESTIMATE -10% to +30% decode; prefill likely lower without repacking | `--no-repack` changes kernels: check | no | GL-6 | Mainline pins thread i to node i mod 2 and splits rows by thread under `--numa` (SOURCE: ggml-cpu.c `set_numa_thread_affinity`, mul_mat_id disables chunking), so pages first touched by the batch threads stay local only when `-t` equals `-tb`. Mixed evidence on other boxes: PR [#27986](https://github.com/ggml-org/llama.cpp/pull/27986) (distribute = mirror at steady state on EPYC) vs [ik #2396](https://github.com/ikawrakow/ik_llama.cpp/pull/2396) (distribute 2% below numactl on Broadwell) |
| 8 | Flash attention off for pure document ingestion | MEASURED +18% prefill at 8K, but -14% decode | none | no | not scheduled | it cannot be switched per request; keep the default (auto = on) unless a job is almost all prefill |
| 9 | Transparent huge pages "always" | ESTIMATE 0-10% | none | system-wide (SIMON ONLY) | Flash-Next FN-10 | box-level; if FN-10 passes it applies here too |
| - | Smaller quants | faster (254-343 GB) | **fail the gate by far**: UD-IQ3_XXS mean KLD 0.273 and UD-Q2_K_XL 0.374 vs full precision, against 0.037 for UD-Q4_K_XL (SOURCE Unsloth table); the gate is KLD <= 0.01 against Q4 | - | not scheduled | the only reason to revisit: a Q2 quant (254 GB) fits one socket and could be mirrored, at top-1 80.9% vs 94.3% |
| - | Does **not** apply | | | | | NUMA mirror (RAM); PrismML's NUMA-aware repack ([PR #251](https://github.com/PrismML-Eng/llama.cpp/pull/251), open) moves only dense-matmul rows (`forward_mul_mat`), not MoE expert rows (SOURCE: the patch); K cache q8_0 (no speed gain on CPU, context is not RAM-limited, and it failed with FA on); `--poll`, ubatch and 72 threads (MEASURED flat); KTransformers and vLLM/SGLang CPU paths (Ampere+/AVX-512 oriented; GLM-5.3 support VERIFY) |

**Hardware upgrades for this model (prices ESTIMATE, VERIFY before buying)**

| Upgrade | Gain for GLM-5.3 | Cost | Notes |
|---|---|---|---|
| 1 TB RAM (16 x 64 GB DDR4 LRDIMM) | a mirror becomes possible: ESTIMATE +15-40% decode (ik mirror measured +15% on 2x Broadwell for Flash-Next; the local-read ceiling is ~2x) | ~$1,000-1,600 used | also gives MiMo room to stay resident; LRDIMM speed at 2 per channel on Haswell VERIFY |
| 2x E5-2699/2696 v4 | ESTIMATE +14% bandwidth (2133 instead of 1866 with 2 DIMMs per channel), +22% cores for prefill | ~$150-300 used | same as the Flash-Next table; board and BIOS support VERIFY |
| A GPU that is not Jarvis's | lever 5 without stopping Jarvis | depends on card | chassis and power limits: wiki gpu-upgrade-options |

## C. Runbook

Order: record facts, the stock baseline with a saved reference (and cache and slot tests), then lossless levers by expected value, then SIMON ONLY items. One lever per step. Each test is the harness `cpu_test.py` in the unit `cpu-test`, CPU only, port 8082, beside Jarvis; it refuses to start when another benchmark unit runs, port 8082 is busy, Jarvis is down or free RAM is short, and it stops itself if Jarvis drops below 75% twice in a row. GLM is slow: most steps take 1-2 hours.
Before every step this must print NONE-ACTIVE:
`systemctl list-units --type=service --state=active --no-legend --plain | grep -E '^(bench-|mtp-test|il-beside|glm-test|fn-test|t27-|big-verify|build-|dl-|kld-|cpu-test)' || echo NONE-ACTIVE`

```text
JARVIS STEP GL-1 of 10: record the starting point (read-only)
Goal: exact bytes per token and how much is routed experts, the indexer settings, free RAM per node, and what the ik build can do.
Precondition: step FN-1 of the Flash-Next runbook done (scripts exist): ls ~/speed/scripts/cpu_test.py ~/speed/scripts/gguf_bytes.py
Commands (one at a time; all read-only):
 1) the NONE-ACTIVE check above
 2) ps -eo rss,args --sort=-rss | head -4 | cut -c1-150
 3) python3 ~/speed/scripts/gguf_bytes.py ~/models/GLM-5.3/UD-Q4_K_XL/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf 1.10 1.48
 4) python3 -c "import sys; sys.path.insert(0, '/home/simon/speed/scripts'); import gguf_bytes as g; kv, _ = g.parse('/home/simon/models/GLM-5.3/UD-Q4_K_XL/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf'); print({k: v for k, v in kv.items() if any(x in k for x in ('indexer', 'nextn', 'expert', 'lora', 'block_count'))})"
 5) grep MemAvailable /proc/meminfo; numactl --hardware | grep -E 'node [01] (size|free)'
 6) grep -E '^(GGML_CUDA|GGML_NATIVE|CMAKE_BUILD_TYPE):' ~/ik_llama.cpp/build/CMakeCache.txt; ~/ik_llama.cpp/build/bin/llama-server --help 2>&1 | grep -c -E -- '--dsa|--mla-use|--spec-type'
 7) df -h --output=avail /home | tail -1
Takes: 2 minutes.
Expected: 2 shows no other process above a few GB (Jarvis's llama-server is mostly on the GPUs). 3 prints the per-token estimate (the benchmark doc used 24.8 GB) and the GB/s that 1.10 and 1.48 t/s imply. 4 prints indexer head count, key length and top-k (ESTIMATE 2048), nextn 1, expert counts. 5 MemAvailable at least 475,000,000 kB (~453 GiB). 6 the ik build flags and a count of 3. 7 at least 20G free for slot files.
PASS: 3 and 4 printed. If 2 shows another big model resident, stop: one big model at a time.
Undo: nothing (read-only).
save_finding(topic="speed-glm53", finding="GL-1: per-token _ GB (routed experts _%, rest _ GB); implied GB/s at 1.10/1.48 = _/_; indexer top-k _, heads _; experts _ used _; MemAvailable _ GiB; node0 free _ MB, node1 free _ MB; ik CUDA=_ flags _", source="gguf_bytes.py, /proc")
```

```text
JARVIS STEP GL-2 of 10: stock baseline beside Jarvis + saved reference + prompt cache + slot save/restore
Goal: the stock server as benchmarked (numactl --preferred=1, 36 threads), a greedy reference for later comparisons (with a run-to-run identity check), whether follow-up requests reuse the prompt, and how long a slot save and restore take.
Preconditions (read-only): GL-1 PASS; NONE-ACTIVE; then
 python3 ~/speed/scripts/cpu_test.py glm-stock-p1 --bin stock --model glm --numa p1 --make-ref glm-stock --tests speed,prefill,cache,slot --max-min 230 --check -- -lm dio -lzm off -t 36 -tb 36 -lv 4 --slot-save-path /home/simon/speed/slots
 must end with: CHECK OK (nothing started)
Command:
 sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=465G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=14400 -p TimeoutStopSec=300 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py glm-stock-p1 --bin stock --model glm --numa p1 --make-ref glm-stock --tests speed,prefill,cache,slot --max-min 230 -- -lm dio -lzm off -t 36 -tb 36 -lv 4 --slot-save-path /home/simon/speed/slots
Watch (every ~15 min): journalctl -u cpu-test -n 12 --no-pager -o cat | cut -c1-200
Done when: systemctl is-active cpu-test prints inactive (or unknown).
Read: D=$(ls -d ~/speed/results/cpu/glm-stock-p1/2* | tail -1); grep -v '^command' $D/summary.txt
Takes: ~1.5-2 h (load 10-20 min; 3 prompts x 2 runs x 256 tokens at ~1 t/s ~26 min; a ~5K-token prefill ~10 min; 3 chat turns ~12 min; slot ~2 min).
Expected: decode ~0.9-1.1 t/s and prefill ~7-9 t/s (MEASURED llama-bench beside Jarvis); "reference re-run identical: 3/3 | saved as reference glm-stock"; prompt cache PASS (MLA caches normally, ESTIMATE); slot: save and restore in seconds, after restore 1-2 tokens re-read, same answer True.
PASS: re-run identical 3/3 AND reference saved AND Jarvis during >= 90% of before AND no STOPPED/ERROR line.
Findings either way: the cache line (FAIL = every follow-up re-reads the whole prompt at ~8 t/s) and the slot line (same answer False or a full re-read = slot files are not usable for this model: tell Simon).
FAIL (re-run not identical): stop and tell Simon; the identity checks below depend on it.
Undo: nothing (results in ~/speed/results/cpu; the slot file ~/speed/slots/cpu_test_slot.bin is overwritten by each run; delete only with Simon's yes).
save_finding(topic="speed-glm53", finding="GL-2 stock p1: decode _/_/_ mean _, prefill _ over _ tok, rerun _/3, cache _ (turns _), slot save _ s _ GiB restore _ s re-read _ same _, load _ s, RSS _ GiB, nodes _, Jarvis _ -> _", source="~/speed/results/cpu/glm-stock-p1/<time>/summary.txt")
```

```text
JARVIS STEP GL-3 of 10: interleave GLM over both sockets beside Jarvis
Goal: numactl --interleave=all instead of --preferred=1, with Jarvis running (MEASURED 1.48 t/s interleaved when Jarvis was stopped).
Preconditions (read-only): GL-2 PASS; NONE-ACTIVE; numactl --hardware | grep 'node 0 free'   (ideally at least 225000 MB; with less, the kernel reclaims cache or puts pages on node 1, the run still works but less evenly)
Command:
 sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=465G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=14400 -p TimeoutStopSec=300 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py glm-il --bin stock --model glm --numa il --ref glm-stock --tests speed,prefill --max-min 230 -- -lm dio -lzm off -t 36 -tb 36
Read: D=$(ls -d ~/speed/results/cpu/glm-il/2* | tail -1); grep -E '^(load|decode|vs ref|prefill|Jarvis|STOP|ERROR)' $D/summary.txt
Takes: ~1-1.5 h.
Expected: decode ~1.3-1.45 t/s (ESTIMATE); every prompt IDENTICAL to the reference (same binary and flags, only page placement differs); Jarvis median a few % lower while it runs.
PASS: decode mean >= 1.15 x GL-2 AND every prompt IDENTICAL AND Jarvis during >= 90% of before. Then --numa il replaces p1 in the steps below; otherwise keep p1 there.
Undo: nothing (test unit only).
save_finding(topic="speed-glm53", finding="GL-3 il beside Jarvis: decode _ (x_ vs GL-2), prefill _, vs ref _, nodes _, Jarvis _ -> _ -> PASS/FAIL", source="~/speed/results/cpu/glm-il/<time>/summary.txt")
```

```text
JARVIS STEP GL-4 of 10: MTP with the model's own head (stock build)
Goal: speculative decoding with blk.78 (no draft file), n-max 1 and 2, then 3 only if 2 beats 1.
Preconditions: GL-2 PASS; NONE-ACTIVE. Use --numa il if GL-3 passed, else --numa p1, in all three runs.
Run one at a time:
 A) sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=465G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=14400 -p TimeoutStopSec=300 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py glm-mtp1 --bin stock --model glm --numa il --ref glm-stock --tests speed --max-min 230 -- -lm dio -lzm off -t 36 -tb 36 --spec-type draft-mtp --spec-draft-n-max 1
 B) the A command with label glm-mtp2 and --spec-draft-n-max 2
 C) only if B beats A: label glm-mtp3 and --spec-draft-n-max 3
Read: for L in glm-mtp1 glm-mtp2 glm-mtp3; do D=$(ls -d ~/speed/results/cpu/$L/2* 2>/dev/null | tail -1); [ -n "$D" ] && echo "== $L" && grep -E '^(load|decode|vs ref|Jarvis|STOP|ERROR)' $D/summary.txt; done
If a run did not start: tail -4 of that run's server.log (MTP layer or memory messages).
Takes: ~45-60 min each (load plus 3 x 256 tokens).
Expected: decode 1.3-1.8x the GL-3 (or GL-2) mean (ESTIMATE; SOURCE ik #1890: 1.8x CPU-only at n_max 2 on GLM-5); draft acceptance ~0.7-0.9; each prompt IDENTICAL or NEAR-TIE.
PASS: best run's mean >= 1.25 x the matching non-MTP mean AND every prompt IDENTICAL or NEAR-TIE (gap <= 0.10) AND Jarvis during >= 85% of before.
FAIL: DIVERGED (gap above 0.10) means MTP changes answers: do not adopt; tell Simon.
Undo: nothing (test units only).
save_finding(topic="speed-glm53", finding="GL-4 MTP: n1 _ (acc _), n2 _ (acc _), n3 _; best x_ vs base; vs ref _ gap _; Jarvis _ -> PASS/FAIL", source="~/speed/results/cpu/glm-mtp*/<time>/summary.txt")
```

```text
JARVIS STEP GL-5 of 10: ik_llama.cpp with real sparse attention (--dsa -mla 1), long prefill
Goal: the biggest long-context lever. A reads a ~16K-token document (600 lines) and then decodes at that depth; B adds ik's MTP if A passes; C (optional) gives the stock number for the same 16K document.
Preconditions (read-only): GL-2 PASS; NONE-ACTIVE; GL-1 command 6 printed 3.
Use --numa il if GL-3 passed, else p1.
 A) sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=465G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=18000 -p TimeoutStopSec=300 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py glm-ik-dsa --bin ik --model glm --numa il --ref glm-stock --tests speed,prefill --prefill-lines 600 --max-min 290 -- --no-mmap -t 36 -tb 36 --dsa -mla 1
 B) only if A passes: the A command with label glm-ik-dsa-mtp2 and --tests speed, adding at the end: --spec-type mtp:n_max=2,p_min=0.0
 C) optional, ~2.5 h: label glm-stock-16k, --bin stock, --tests prefill --prefill-lines 600 --max-min 290, server flags -lm dio -lzm off -t 36 -tb 36
Read: for L in glm-ik-dsa glm-ik-dsa-mtp2 glm-stock-16k; do D=$(ls -d ~/speed/results/cpu/$L/2* 2>/dev/null | tail -1); [ -n "$D" ] && echo "== $L" && grep -E '^(load|decode|vs ref|prefill|Jarvis|STOP|ERROR)' $D/summary.txt; done
If A did not start: D=$(ls -d ~/speed/results/cpu/glm-ik-dsa/2* | tail -1); tail -4 $D/server.log | cut -c1-200
Takes: A ~1.5-2 h, B ~1 h, C ~2.5 h.
Expected (ESTIMATE, scaled from ik #2074 on a CPU with ~2x this box's compute): A depth-0 decode within 10% of GL-3; 16K prefill average ~10-15 t/s (stock ~4-5 average, from the MEASURED 10.1 at depth 0 and 2.51 at 16K); decode after 16K ~1.0-1.3 (stock 0.74 beside Jarvis, 1.00 interleaved, MEASURED); prompts NEAR-TIE or IDENTICAL vs the stock reference.
PASS A: 16K prefill average >= 2 x stock (C if run, else 4.5 t/s) AND decode after 16K >= 1.2 x the stock figure AND every prompt IDENTICAL or NEAR-TIE. PASS B: decode >= 1.25 x A and IDENTICAL/NEAR-TIE.
FAIL: DIVERGED anywhere -> not adoptable under the quality rule; record the gap, tell Simon.
Undo: nothing (test units only).
save_finding(topic="speed-glm53", finding="GL-5 ik dsa: d0 decode _, 16K prefill avg _ (stock _), decode at 16K _ (stock _), vs ref _; ik MTP2 _ (x_) -> PASS/FAIL", source="~/speed/results/cpu/glm-ik-dsa*/<time>/summary.txt")
```

```text
JARVIS STEP GL-6 of 10: first-touch NUMA placement with the stock build
Goal: let each weight page land on the node whose threads read it: page cache emptied for the GLM files, mmap, no repacking, --numa distribute, -t 36 -tb 36 (the same thread count for batch and decode, so the row split that places the pages is the split that later reads them).
Preconditions (read-only): GL-2 PASS; NONE-ACTIVE; grep -l GLM-5.3 /proc/[0-9]*/maps 2>/dev/null | wc -l   prints 0
Command:
 sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=465G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=14400 -p TimeoutStopSec=300 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py glm-ft-distr --bin stock --model glm --numa none --evict --warm 2 --ref glm-stock --tests speed,prefill --max-min 230 -- -lm mmap -lzm off --no-repack -t 36 -tb 36 --numa distribute
Read: D=$(ls -d ~/speed/results/cpu/glm-ft-distr/2* | tail -1); grep -E '^(load|decode|vs ref|prefill|Jarvis|STOP|ERROR)' $D/summary.txt
Takes: ~1.5-2 h; the first requests are slow while 435 GiB is read from the NVMe in small pieces (mmap under --numa reads without prefetch).
Expected: per-node MB roughly equal; decode ESTIMATE -10% to +30% vs the better of GL-2/GL-3; prefill likely lower than with repacking; prompts IDENTICAL or NEAR-TIE (different kernels without repacking).
PASS: decode >= 1.1 x the better of GL-2/GL-3 AND prefill >= 0.85 x it AND every prompt IDENTICAL or NEAR-TIE. Otherwise keep the GL-3/GL-2 placement.
Undo: nothing (the page cache refills on the next load).
save_finding(topic="speed-glm53", finding="GL-6 first-touch: decode _ (x_), prefill _ (x_), nodes _, vs ref _ -> PASS/FAIL", source="~/speed/results/cpu/glm-ft-distr/<time>/summary.txt")
```

```text
JARVIS STEP GL-7 of 10: two jobs at once (stock, --parallel 2)
Goal: total throughput when the orchestrator runs two GLM jobs together. Skip this step if it never will.
Preconditions: GL-2 PASS; NONE-ACTIVE. Use --numa il if GL-3 passed, else p1.
Command:
 sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=465G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=14400 -p TimeoutStopSec=300 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py glm-par2 --bin stock --model glm --numa il --ref glm-stock --tests par --max-min 230 -- -lm dio -lzm off -t 36 -tb 36 --parallel 2
Read: D=$(ls -d ~/speed/results/cpu/glm-par2/2* | tail -1); grep -E '^(load|2 slots|Jarvis|STOP|ERROR)' $D/summary.txt
Takes: ~45 min.
Expected (ESTIMATE): two at once 1.2-1.5x the single-request t/s in total, each job slower.
PASS: total >= 1.2 x single -> use 2 slots for queued GLM jobs (stock only: ik's --dsa needs one sequence). Otherwise one job at a time.
Undo: nothing.
save_finding(topic="speed-glm53", finding="GL-7 two slots: single _ t/s, two at once _ t/s total (x_) -> PASS/FAIL", source="~/speed/results/cpu/glm-par2/<time>/summary.txt")
```

```text
JARVIS STEP GL-8 of 10: SIMON ONLY - Jarvis must not run this. GPU hybrid in a night window (Jarvis off)
Why SIMON ONLY: it needs both GPUs, so Jarvis must be stopped; the benchmark runner stops and restarts Jarvis for "gpu" jobs between 1 and 7 AM Central.
Goal: measure what the V100s add when they hold every non-expert tensor (attention, indexer, shared expert, dense layers) and do the big prefill batches, while the routed experts stay in RAM. This fixes the night-1 test design: -ncmoe 79 keeps every MoE layer's experts on the CPU.
Preconditions (read-only):
 1) systemctl is-active bench-queue prints inactive (never edit the queue while the runner runs)
 2) GL-1: "everything else" at most ~24 GB (two 16 GB cards minus buffers)
Do: add these two lines to ~/bench/queue.txt, then start the runner in the night window as usual (HANDOFF):
 glm-g1-hybrid gpu 3 -m /home/simon/models/GLM-5.3/UD-Q4_K_XL/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf -lm dio -lzm off -ngl 99 -ncmoe 79 -t 36 -b 4096 -ub 512,4096 -p 4096 -n 64 -r 1
 glm-g2-hybrid-d16k gpu 4 -m /home/simon/models/GLM-5.3/UD-Q4_K_XL/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf -lm dio -lzm off -ngl 99 -ncmoe 79 -t 36 -b 4096 -ub 4096 -p 4096 -n 64 -d 16384 -r 1
Read (next morning): python3 ~/bench/summary.py ~/bench/results/glm-g1-hybrid/*.jsonl ~/bench/results/glm-g2-hybrid-d16k/*.jsonl
Takes: ~1-2 h inside the window.
Expected (ESTIMATE): tg64 ~2.0-2.5 t/s (vs 1.48 CPU-only interleaved, MEASURED); pp4096 at ub 4096 ~50-120 t/s (vs 7.6), at ub 512 near CPU speed; at 16K depth prefill stays close to the depth-0 figure.
PASS/FAIL: none; the numbers tell Simon whether long GLM jobs are worth a Jarvis-off window. If a job fails with a CUDA allocation error, the non-expert part did not fit: record the error line from ~/bench/queue.log.
Undo: delete the two lines from ~/bench/queue.txt (a finished label is skipped anyway).
save_finding(topic="speed-glm53", finding="GL-8 hybrid: tg _ (vs 1.48), pp4096 ub512 _ / ub4096 _ (vs 7.6), d16K pp _ tg _", source="~/bench/results/glm-g*-hybrid*")
```

```text
JARVIS STEP GL-9 of 10: SIMON ONLY - Jarvis must not run this. A GLM job server you start when needed
Why SIMON ONLY: it creates a new systemd unit and uses ~430 GiB of RAM while running.
Goal: one unit with the winning flags, NOT started at boot; started only when no other big model runs (stop flash-next first).
Preconditions (read-only): GL-2 PASS and the chosen variant PASSED (GL-3/4/5/6); NONE-ACTIVE; systemctl is-active flash-next prints inactive; grep MemAvailable /proc/meminfo at least 475,000,000 kB.
Commands (Simon):
 1) sudo tee /etc/systemd/system/glm-jobs.service >/dev/null <<'UNIT_END'   then paste the unit text from section D (ExecStart swapped for the variant that won), then a line UNIT_END
 2) sudo systemctl daemon-reload && sudo systemctl start glm-jobs
 3) for i in $(seq 90); do curl -sf localhost:8081/health && break; sleep 20; done    (loading takes 10-20 min)
 4) curl -s localhost:8081/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"Say OK."}],"max_tokens":64}' | python3 -c "import json,sys;r=json.load(sys.stdin);print(r['choices'][0]['message'].get('content'),r['timings']['predicted_per_second'])"
 5) curl -s localhost:8080/health    (Jarvis still answers)
 6) when finished with the jobs: sudo systemctl stop glm-jobs     (do NOT enable it at boot)
Expected: 3 prints {"status":"ok"}; 4 prints an answer at about the winning step's speed.
PASS: 3, 4 and 5 succeed. FAIL: journalctl -u glm-jobs -n 30 --no-pager, then the rollback.
Rollback: sudo systemctl stop glm-jobs && sudo mv /etc/systemd/system/glm-jobs.service ~/speed/glm-jobs.service.off && sudo systemctl daemon-reload
Notes: port 8081 is shared with flash-next on purpose (only one big model runs at a time), so they must never run together; t27_window.py also refuses while 8081 is busy.
save_finding(topic="speed-glm53", finding="GL-9 glm-jobs unit created with variant _, probe _ t/s", source="systemctl status glm-jobs")
```

```text
JARVIS STEP GL-10 of 10: check real GLM jobs afterwards (read-only)
Goal: confirm the speed and the prompt/slot reuse hold in real jobs.
Precondition: glm-jobs has run at least one real job since GL-9.
Commands:
 1) journalctl -u glm-jobs --since "-7d" -o cat --no-pager | python3 ~/speed/scripts/j27_logstats.py
 2) journalctl -u glm-jobs --since "-7d" -o cat --no-pager | grep -c -E 'GGML_ASSERT|ggml_abort|out of memory|Segmentation'
 3) ls -la ~/speed/slots | tail -5
Takes: 1 minute.
Expected: 1 prints decode and prompt-eval percentiles (j27_logstats.py parses stock log lines; for an ik unit it may print nothing: then journalctl -u glm-jobs -n 30); 2 prints 0; 3 lists the slot files the jobs saved (if the orchestrator uses them).
PASS: token-weighted decode >= 0.9 x the winning step's decode AND 2 prints 0. FAIL: tell Simon; rollback is in GL-9.
Undo: nothing (read-only).
save_finding(topic="speed-glm53", finding="GL-10 real jobs: decode p50 _ weighted _, prompt-eval p50 _ ms, crash lines _ -> PASS/FAIL", source="journalctl glm-jobs 7d")
```

## D. Proposed final config (PROPOSED until GL-2..GL-6 measure it)

If ik's sparse attention passes (GL-5), the job server is ik with `--dsa -mla 1`, one slot, slot files enabled. ESTIMATE: ~1.3-1.45 t/s decode at depth 0 (x1.3-1.8 with MTP if GL-5 B passes), a 16K document read in ~20-30 min instead of ~1 h.

```ini
[Unit]
Description=GLM-5.3 job server (llama-server on 127.0.0.1:8081, start by hand, one big model at a time)
After=network-online.target llama-server.service

[Service]
User=simon
Group=simon
Environment=CUDA_VISIBLE_DEVICES=
ExecStart=/usr/bin/numactl --interleave=all /home/simon/ik_llama.cpp/build/bin/llama-server -m /home/simon/models/GLM-5.3/UD-Q4_K_XL/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf --no-mmap -t 36 -tb 36 --dsa -mla 1 -c 65536 --parallel 1 --jinja --host 127.0.0.1 --port 8081 --slot-save-path /home/simon/speed/slots
MemoryMax=470G
MemorySwapMax=0
OOMScoreAdjust=500
Nice=5
```

(No `[Install]` section: it is never started at boot.) Add `--spec-type mtp:n_max=2,p_min=0.0` if GL-5 B passed. If GL-3 failed, use `--preferred=1` instead of `--interleave=all`.

If ik fails GL-5, the stock job server: `ExecStart=/usr/bin/numactl --interleave=all /home/simon/llama.cpp/build/bin/llama-server -m <same model> -lm dio -lzm off -t 36 -tb 36 -c 32768 --parallel 1 --jinja --host 127.0.0.1 --port 8081 --slot-save-path /home/simon/speed/slots` plus `--spec-type draft-mtp --spec-draft-n-max <best from GL-4>` if GL-4 passed, and `--parallel 2` if GL-7 passed. ESTIMATE ~1.35-1.45 t/s (x1.3-1.8 with MTP). `-c 32768` because stock prefill makes longer contexts impractical (a 32K document is ~2.5-3 h, section A).

Why: `-t 36 -tb 36` (MEASURED: decode flat from 18 to 36 threads, prefill best at 36; 72 adds 1%); flash attention left at its default (auto = on; MEASURED +17% decode at 8K); `Nice=5` so Jarvis's CPU work wins any contention; `MemorySwapMax=0` so weights never swap; port 8081 shared with flash-next because only one big model runs at a time.

## E. Open questions and VERIFY items (each with a read-only command)

1. Exact bytes per token and routed-expert share: GL-1 command 3. The 24.8 GB figure and every decode ESTIMATE move with it.
2. Indexer top-k and whether GLM-5.3 uses shared indexer layers: GL-1 command 4 (keys containing "indexer").
3. Has ik fixed sparse attention with more than one sequence (needed for `--parallel 2` with `--dsa`)? `git -C ~/ik_llama.cpp log --oneline | grep -i -E 'dsa' | head -8` and read the titles.
4. Does the stock slot file include the indexer cache? GL-2's slot line ("same answer True" after restore = yes in practice).
5. KV bytes per token and load time: after GL-2, `D=$(ls -d ~/speed/results/cpu/glm-stock-p1/2* | tail -1); grep -m4 -iE 'KV (self|buffer) size|llama_kv_cache|load time' $D/server.log | cut -c1-200`.
6. Is the ik build compiled for this CPU (and with or without CUDA)? GL-1 command 6.
7. KTransformers / vLLM / SGLang support for GLM-5.3 on AVX2 without AVX-512: check their repositories (no box command).
8. Whether mainline gains real sparse attention (skipping masked keys in the math, not just masking): search llama.cpp pull requests for "DSA" and "indexer" before the next GLM session (no box command).
