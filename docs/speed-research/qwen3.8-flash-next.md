# Qwen3.8-Flash-Next (UD-Q4_K_XL, + GSQ-RCO IQ3_XXS / Q2_0, + MTP heads): speed research and runbook

For Simon. Written 2026-09-25 (evening, Central time). Labels: MEASURED (on jarvis-1, with date), SOURCE (link), ESTIMATE (arithmetic shown), VERIFY (not checked yet; a read-only command is given in section E).
Role assumed here: the always-on CPU worker that runs BESIDE Jarvis (the orchestrator plan in HANDOFF: "long-context always-on worker should use Flash-Next on CPU (port 8081)"). So most steps run without stopping Jarvis, and Jarvis may run them itself. Steps that stop Jarvis or change the box are marked SIMON ONLY.
Numbers below come from the benchmark session's results (docs/benchmarks/qwen3.8-flash-next.md on branch claude/new-session-uyo1y3, read 2026-09-25 at commit 7be739a). That session is still working on this model (ik_llama.cpp head-to-head queued at 5:49 PM CT). Nothing in this runbook runs while one of its units is active.

## A. Current state

**Model files** (MEASURED 2026-09-25): unsloth UD-Q4_K_XL, 4 shards, 111,334,654,784 B (103.7 GiB), sha256-verified 12:33 PM CT. Draft heads in `~/models/Qwen3.8-Flash-Next-unsloth/MTP/` (6 files; shared-Q8_0 is the one measured). GSQ-RCO IQ3_XXS (75.8 GB) and Q2_0 (66.4 GB) are on the model drive only (`/mnt/models`, read-only).
Architecture (SOURCE: the wiki page qwen38-flash-next, which checked it against the Qwen model card): 125B total, 6B active, 48 layers = 12 x (3 Gated DeltaNet + 1 Qwen Sparse Attention), 512 experts with 10 routed + 1 shared active, a 51B n-gram hash-embedding table (read sparsely), a separate 4B MTP module.

**Builds on the box**: stock `~/llama.cpp` at f4e276a20 (qwen4exp supported, no Flash-Next MTP); `~/llama.cpp-fnmtp` = llama.cpp PR #28243 at 6fcaa16f4, CPU-only build (MTP for this model); `~/ik_llama.cpp` at 1aaf7105 (built 5:49 PM CT; ik has qwen4exp and merged MTP for it).

**Measured speed** (all MEASURED on jarvis-1, 2026-09-25, by the benchmark session; CPU only, GPUs hidden, Jarvis running):

| Setup | Decode t/s | Prefill t/s | Notes |
|---|---|---|---|
| Socket 1 only, stock, 18 threads (llama-bench tg128 / pp512) | 4.10 (12:42 PM), 4.19 (4:33 PM control) | 29.35 | run-to-run within 2% |
| Socket 1, threads 9 / 12 / 16 / 18 / 36 | **4.38** / 4.32 / 4.19 / 4.17 / 3.93 | 16.94 / 22.01 / 28.01 / 29.35 / **31.67** | fewer threads decode faster; prefill wants all 36 |
| Socket 1, ubatch 512 / 1024 / 2048 / 4096 (pp4096) | - | **27.79** / 26.59 / 26.28 / 25.34 | default 512 best |
| Socket 1, flash attention on vs off at 8K depth | 4.01 vs 3.88 | 23.25 vs 24.31 | near neutral |
| Socket 1, K/V q8_0 vs f16 | 4.16 vs 4.17 | 29.03 vs 29.35 | no speed gain |
| Socket 1, depth 0 / 16K / 32K / 64K | 4.17 / 3.87 / 3.58 / 2.91 | 29.35 / 20.60 / 16.20 / 10.66 | a 64K prompt took ~70 min to fill |
| Socket 1, llama-server, PR build, MTP off (300 tokens, 3 prompts) | 4.30 mean | ~25 | -t 12 -tb 36 |
| Same, MTP shared-Q8 n-max 1 / 2 / 3 / 4 | 5.39 / 5.71 / **6.73** / 6.05 | ~25 | n-max 3 = **1.57x** (reasoning 7.62 = 1.78x) |
| Both sockets interleaved (numactl --interleave=all), threads 12 / 18 / 24 / 36 | 5.51 / **5.60** / 5.23 / 5.03 | 23.06 / 30.89 / 39.30 / **50.66** | +28% decode, +60% prefill vs socket 1; Jarvis median -3%, worst probe -15% |

Output check (MEASURED 5:19 PM CT): all 6 MTP configs gave identical text to each other; all differed from MTP-off at the same token, which the benchmark session judged a near-tie ("coherent, likely benign"). The results file does not record the top-2 logprob gap at that token, and a run-to-run identity check with MTP off is still owed. FN-3 and FN-4 measure both.

**Not measured yet**: MTP together with interleaving; ik_llama.cpp (queued by the benchmark session); NUMA mirror or first-touch placement; prompt-cache reuse on this hybrid model (the biggest practical risk); the GSQ-RCO quants; 2 slots; one GPU helping (needs Jarvis off).

**Limits, with arithmetic**
- Bytes read per token (ESTIMATE, settled by step FN-2): the two GSQ-RCO files give 75.8 GB at 3.00 bpw and 66.4 GB at 2.40 bpw, so 9.4 GB per 0.6 bpw = 15.7 GB per bpw = 125B quantized parameters plus a fixed ~28.8 GB (the n-gram table and vision projector). If UD-Q4_K_XL stores the table the same way, the rest is 111.3 - 28.8 = 82.5 GB for 125B = 5.3 bpw, so 6B active x 5.3/8 = ~4.0 GB per token. If unsloth stored the table at 6 bpw (38.4 GB, like the AtomicChat build in the wiki), it is 72.9 GB = 4.7 bpw = ~3.5 GB per token. Range 3.5-4.0 GB.
- Bandwidth reached (ESTIMATE from the above): socket 1: 4.38 t/s x 3.5-4.0 GB = 15-18 GB/s = 52-59% of the 29.5 GB/s STREAM Triad (MEASURED Sep 23 after the uncore fix). Interleaved: 5.60 x 3.5-4.0 = 20-22 GB/s = only 33-38% of the 59.5 GB/s two-socket Triad. Half of every interleaved read crosses QPI, and that shows.
- Ceiling if every thread read only local memory (ESTIMATE): 2 sockets x 15-18 GB/s = 30-35 GB/s, / 3.5-4.0 GB = **~7.5-10 t/s** without MTP. That is the prize for NUMA mirroring or first-touch placement. With MTP x1.57 on top: ~12-15 t/s (ESTIMATE, upper bound).
- Why MTP gives 1.57x and not 3x (ESTIMATE): at n-max 3, 219 of 239 drafts were accepted on the reasoning prompt, ~3.7 tokens per verify step. But a 4-token verify step reads up to ~4 x 10 = 39 of 512 experts per layer instead of 10, so it costs roughly 0.45 + 0.55 x 3.9 = 2.6 single-token steps if routed experts are ~55% of the bytes (FN-2 gives the real share). More bandwidth helps MTP and plain decode alike.
- Prefill is compute-bound: 50.66 t/s interleaved means a 2,500-token system prompt costs ~50 s and a 16K prompt ~5 min. **Re-processing a prompt is the most expensive thing this model does**, so prompt-cache reuse matters more than any decode lever for multi-turn and agent use.
- RAM: ~104 GiB resident with `-lm dio -lzm off` (the n-gram table fully resident). A mirror doubles that to ~208 GiB. Jarvis uses little host RAM. The "one big model at a time" rule still applies to GLM/MiMo tests.

## B. Levers, ranked for the beside-Jarvis worker role

| # | Lever | Expected gain | Quality risk | Downtime? | Effort | Evidence |
|---|---|---|---|---|---|---|
| 1 | **Prompt-cache reuse** (context checkpoints; defaults `-ctxcp 32 -cms 8192 -cram 8192`) | Follow-up requests re-read ~10-100 tokens instead of the whole prompt: a 2,500-token system prompt drops from ~50 s to ~1 s of prefill (ESTIMATE at 50 t/s) | none (same state restored) | no | test only (FN-3) | SOURCE: llama.cpp server code creates a checkpoint at the last user message and 4 and 4+n_ubatch tokens before the prompt end ([server-context.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-context.cpp), PR [#20288](https://github.com/ggml-org/llama.cpp/pull/20288)); `llm_arch_supports_rs_rollback` lists QWEN4EXP. VERIFY on the box: the wiki rates hybrid models HIGH RISK for full re-processing |
| 2 | **MTP n-max 3, shared-Q8 head** | MEASURED 1.57x on socket 1 (4.30 to 6.73, Sep 25). ESTIMATE with interleave: 5.60 x 1.57 = ~8.8 t/s | output differs from MTP-off at a near-tie token (MEASURED); gap size VERIFY in FN-4 | no | FN-4 | PR [#28243](https://github.com/ggml-org/llama.cpp/pull/28243) (OPEN, head 6fcaa16f4 = the box's build; known issues listed there: greedy divergence at n-max >= 3 on Metal, --fit ignores the head) |
| 3 | **ik_llama.cpp** (engine) incl. its merged MTP for this model | ESTIMATE prefill +20-100%, decode +0-20%; MTP with per-step state saving (no re-decode on rejection) | different kernels, so near-tie differences possible; check | no | FN-5 (after the benchmark session's llama-bench head-to-head) | ik MTP for qwen4exp merged Sep 2 ([#2369](https://github.com/ikawrakow/ik_llama.cpp/pull/2369)), shared heads without token_embd Sep 14 (#2403), per-step checkpoints for the n-gram layer Sep 14 ([#2412](https://github.com/ikawrakow/ik_llama.cpp/pull/2412)), depth-constant decode attention Sep 3 (#2404). MTP is single-slot only (#2369). `--spec-ckpt-mode auto` picks "gpu-fallback" (re-decode on rejection) when not fully on GPU, so pass `per-step` on CPU (ik help text) |
| 4 | **NUMA mirror** (ik PR #2396: a weight copy per socket) | SOURCE: +15.1% decode over `numactl` and +17.6% over `--numa distribute`, on 2x Xeon E5-2697A v4 (Broadwell, DDR4-2133) running **this model** (UD-Q3_K_XL, attention on an RTX 3090); gains shrink with context on CPU-only runs. ESTIMATE here 6.4-8 t/s | none expected (same math); check | no | FN-7 build, FN-8 test | [ik PR #2396](https://github.com/ikawrakow/ik_llama.cpp/pull/2396) OPEN (head commit 1efab5e5, dated Sep 2); I checked with `git merge-tree` that it merges without conflicts onto ik 1aaf7105. Needs mmap (not `--no-mmap`), 2x RAM (~208 GiB). Mainline's draft [PR #27986](https://github.com/ggml-org/llama.cpp/pull/27986) is the alternative |
| 5 | **First-touch `--numa distribute`** (stock, no fork) | ESTIMATE -5% to +20%. SOURCE both ways: the author of PR #27986 found steady-state distribute equal to mirror on 2x EPYC 7532 (MoE 16.9 vs 16.4 t/s); on the Broadwell box above, distribute was ~2% slower than numactl | `--no-repack` changes kernels: check | no | FN-6 | Mainline has no NUMA-aware allocation: repacked Q4_K weights are written by the loading thread, so first-touch only works with mmap AND `--no-repack` (`-nr`); llama-bench has no repack switch, so this needs llama-server (SOURCE: [repack.cpp](https://github.com/ggml-org/llama.cpp/blob/master/ggml/src/ggml-cpu/repack.cpp), llama-mmap.cpp disables prefetch and sets MADV_RANDOM under --numa) |
| 6 | **Threads for MTP verify** (`-tb`) | ESTIMATE ±5-10% | none | no | FN-4 option C | verify batches have >1 token, so they run with `-tb` threads, not `-t` (SOURCE: `llama_context::graph_compute(gf, batched)` in [llama-context.cpp](https://github.com/ggml-org/llama.cpp/blob/master/src/llama-context.cpp)). 36 threads decode 9% slower than 12 on socket 1 (MEASURED), but prefill needs 36 |
| 7 | **Transparent huge pages "always"** | ESTIMATE 0-10% | none | no, but system-wide setting (SIMON ONLY) | FN-10 | mainline never asks for huge pages for model buffers (grep of ggml/src finds MADV_HUGEPAGE only in a RISC-V backend); box is THP=madvise. ik has a per-process `-thp` switch (benchmark job ik-fn-a5-thp) |
| 8 | **GSQ-RCO IQ3_XXS** (75.8 GB, 3.0 bpw) | ESTIMATE decode +15-40% (2.3-2.6 GB instead of 3.5-4.0 GB per token, but IQ3_XXS dot products cost more compute than repacked Q4_K) | **lossy**. ESTIMATE: fails the KLD gate. Unsloth's table for this model (SOURCE [unsloth docs, via search snippet](https://unsloth.ai/docs/models/qwen3.8-next)): UD-Q4_K_XL mean KLD 0.047 and top-1 92.3% vs BF16; UD-IQ3_XXS mean KLD 0.165. Vendor claim for GSQ-RCO IQ3_XXS: 99.4% of the base task average ([card](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF)) | no | FN-9 | Gate: KLD vs UD-Q4_K_XL, top-1 >= 99% and mean KLD <= 0.01, or equal scores on Simon's quality suite |
| - | GSQ-RCO **Q2_0** | ESTIMATE slower than Q4 here despite fewer bytes | lossy | - | not scheduled | x86 has no SIMD kernel for Q2_0 (`ggml_vec_dot_q2_0_q8_0_generic` aliased for x86 in [arch-fallback.h](https://github.com/ggml-org/llama.cpp/blob/master/ggml/src/ggml-cpu/arch-fallback.h)); ik cannot load it (type 42 does not exist in ik). The vendor's fast-prefill figure is a GPU number |
| 9 | **2 slots** (`--parallel 2`) | ESTIMATE +10-40% total throughput for two jobs at once, each job slower (two tokens read ~2x the routed experts) | none | no | FN-3 option (`par` test) | only useful if the orchestrator runs two jobs at once; ik MTP refuses `-np > 1` |
| 10 | **Shorter reasoning** (reasoning effort) | ESTIMATE 2-5x less wall time on easy tasks (fewer tokens) | **lossy**: needs equal scores on Simon's quality suite per task type | no | orchestrator setting, not a runbook step | Artificial Analysis calls this model "very verbose" (wiki qwen38-flash-next). VERIFY the template reads `reasoning_effort` (section E) |
| 11 | **One V100 helping** (all non-expert tensors on the GPU, experts on CPU, large-batch prefill offload) | ESTIMATE decode +40-80%, prefill 50 to 200-500 t/s with `-ub 4096` (PCIe 3.0 x16 ~12 GB/s moving the expert weights once per 4,096-token batch) | none | **yes (GPUs are full with Jarvis)** | FN-11, SIMON ONLY, informational | SOURCE for the shape: 2x Broadwell + one RTX 3090, this model at UD-Q3_K_XL: 22.4 t/s decode (ik PR #2396). Only matters if Simon ever frees a card (orchestrator "single-card 27B" idea) |
| 12 | BIOS snoop mode (Home Snoop instead of the Haswell-EP default Early Snoop) | ESTIMATE 0-5% memory bandwidth, possibly more on cross-socket reads | none | **yes, reboot (SIMON ONLY)** | not scheduled | SOURCE: Home Snoop "slightly better memory bandwidth" for bandwidth-sensitive work (Dell HPC BIOS tuning paper for Haswell, [via search](https://dl.dell.com/manuals/all-products/esuprt_solutions_int/esuprt_solutions_int_solutions_resources/high-computing-solution-resources_white-papers6_en-us.pdf); [Molka et al. ICPP 2015](https://tu-dresden.de/die_tu_dresden/zentrale_einrichtungen/zih/forschung/projekte/benchit/2015_ICPP_authors_version.pdf)). Current setting VERIFY in BIOS setup |
| - | Does **not** help / does not apply | | | | | K/V q8_0 (no speed gain MEASURED, and lossy); bigger ubatch (MEASURED slower); `--poll` (MEASURED no effect); n-gram speculation stacked on MTP (on hybrid models a rejection forces a checkpoint restore and replay; the 27B lost 37%, MEASURED Sep 22); `--cache-reuse` (KV shifting does not work for recurrent layers); GPU expert-cache PRs and GDN chunked CUDA prefill ([#26001](https://github.com/ggml-org/llama.cpp/pull/26001), open, Ampere+ only) need GPUs that Jarvis holds or V100 cannot use; KTransformers / vLLM / SGLang CPU paths: no qwen4exp support found (VERIFY), and their CPU kernels target AVX-512/AMX, which Haswell lacks |

**Hardware upgrades (costed separately; prices are ESTIMATE, VERIFY before buying)**

| Upgrade | What it buys for this model | Cost (ESTIMATE) | Notes |
|---|---|---|---|
| 2x Xeon E5-2699 v4 / 2696 v4 (Broadwell, 22 cores) | ESTIMATE: the current DIMMs (rated 2133, running 1866 because of 2 per channel on Haswell) would run 2133 with 2 per channel on Broadwell-EP, as typical Broadwell board tables list = +14% bandwidth, ~+14% decode; +22% cores for prefill | ~$150-300 used for the pair | board ASUS Z10PG-D16 supports E5-2600 v4 and DDR4-2400 with v4 (SOURCE: [memory compatibility listings for Z10PG-D16](https://www.amazon.com/ESC4000-Z10PG-D16-PC4-2400-Registered-PARTS-QUICK/dp/B01F490YAM)); VERIFY the 2-per-channel speed in the board manual and that BIOS 3803 supports v4 (ASUS CPU support list) |
| 1 DIMM per channel, 8x 64 GB DDR4-2400 LRDIMM (with v4 CPUs) | 2400 instead of 1866 = +29% bandwidth, ~+25% decode (ESTIMATE); RAM stays 512 GB | ~$500-800 used | halves DIMM count; only worth it together with v4 CPUs |
| Freeing one V100 for Flash-Next (Jarvis on one card) | lever 11: ESTIMATE decode +40-80%, prefill up to ~10x | $0 hardware, but it is a Jarvis architecture change | measure first (FN-11) |

## C. Runbook

Order: deliver scripts, record the baseline, then the lossless levers from most to least likely, then the lossy/SIMON ONLY ones. One lever per step. Every test runs the harness `cpu_test.py` as the unit `cpu-test` beside Jarvis (CPU only, GPUs hidden, port 8082). The harness refuses to start if another benchmark unit is active, port 8082 is busy, Jarvis is not running, or free RAM is too low; it probes Jarvis every 90 s and stops itself if Jarvis drops below 75% twice in a row. Read results with the Read line in each step. If a unit is still running when you check, wait 10 minutes and check again.

The check used by every step (must print NONE-ACTIVE):
`systemctl list-units --type=service --state=active --no-legend --plain | grep -E '^(bench-|mtp-test|il-beside|glm-test|fn-test|t27-|big-verify|build-|dl-|kld-|cpu-test)' || echo NONE-ACTIVE`

```text
JARVIS STEP FN-1 of 13: SIMON STEP - put the two test scripts on the box
Who: Simon, in his own SSH terminal (Jarvis cannot paste heredocs). Jarvis does nothing in this step.
Goal: write ~/speed/scripts/cpu_test.py (the test harness; runs beside Jarvis, never touches llama-server) and ~/speed/scripts/gguf_bytes.py (read-only size calculator).
Precondition: none. It only creates files under ~/speed.
Do: open docs/speed-research/scripts/deliver-fn.sh (580 lines) and paste all of it into the terminal.
Takes: seconds.
Expected: the last two lines printed are
 cpu_test.py: 456 lines, 26652 bytes, cd62e4e24030dc1e
 gguf_bytes.py: 115 lines, 6059 bytes, ef47398d2254c477
PASS: both lines match exactly. FAIL: paste again; if it still differs, stop and tell Claude.
Undo: rm ~/speed/scripts/cpu_test.py ~/speed/scripts/gguf_bytes.py (Simon's yes).
save_finding(topic="speed-flashnext", finding="FN-1 scripts delivered, checksums cd62e4e24030dc1e and ef47398d2254c477 match", source="deliver-fn.sh")
```

```text
JARVIS STEP FN-2 of 13: record the starting point (read-only)
Goal: exact bytes read per token (sets every speed ceiling), free RAM, kernel settings, what exists on disk, and whether the benchmark session's ik results are in.
Precondition: step FN-1 PASS. Nothing else; every command is read-only.
Commands (one at a time):
 1) systemctl list-units --type=service --state=active --no-legend --plain | grep -E '^(bench-|mtp-test|il-beside|glm-test|fn-test|t27-|big-verify|build-|dl-|kld-|cpu-test)' || echo NONE-ACTIVE
 2) python3 ~/speed/scripts/gguf_bytes.py ~/models/Qwen3.8-Flash-Next-unsloth/UD-Q4_K_XL/Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf 4.38 5.60 6.73
 3) grep -E '^(MemAvailable|AnonHugePages)' /proc/meminfo; cat /sys/kernel/mm/transparent_hugepage/enabled /proc/sys/kernel/numa_balancing
 4) ls -l ~/llama.cpp-fnmtp/build/bin/llama-server ~/ik_llama.cpp/build/bin/llama-server ~/models/Qwen3.8-Flash-Next-unsloth/MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf 2>&1 | cut -c1-170
 5) ls ~/bench/results | grep -E '^ik-fn' | tr '\n' ' '; echo; tail -3 ~/bench/queue.log 2>/dev/null | cut -c1-200
 6) find /mnt/models -maxdepth 5 -iname '*GSQ-RCO*.gguf' -printf '%s %p\n' 2>/dev/null | grep -i flash | head -6
 7) df -h --output=avail,target /home | tail -1; head -c 40000000 ~/models/Qwen3.8-Flash-Next-unsloth/UD-Q4_K_XL/Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf | grep -a -c reasoning_effort
Takes: about 2 minutes (command 7 reads only the first 40 MB of the first shard, where the chat template lives).
Expected: 1 prints NONE-ACTIVE (if not, the benchmark session is busy: record and stop here). 2 prints a "per-token read estimate" (ESTIMATE 3.5-4.0 GB) and the GB/s each measured speed implies. 3 MemAvailable above 136,000,000 kB (130 GiB), THP "[madvise]", numa_balancing 0. 4 three files listed. 5 the ik-fn result folders done so far. 6 up to two GSQ-RCO paths (IQ3_XXS, Q2_0). 7 free space, and a count above 0 if the chat template knows reasoning_effort.
PASS: command 2 printed the estimate. This step records facts; there is nothing to fix.
Undo: nothing (read-only).
save_finding(topic="speed-flashnext", finding="FN-2: per-token _ GB (routed-expert share _%, rest _ GB); implied GB/s at 4.38/5.60/6.73 = _/_/_; MemAvailable _ GiB; THP _; numa_balancing _; ik results: _; GSQ-RCO: _; free /home _; reasoning_effort in template: _", source="gguf_bytes.py, /proc")
```

```text
JARVIS STEP FN-3 of 13: stock baseline beside Jarvis + reference output + prompt-cache test
Goal: (a) the stock server speed on both sockets (numactl interleave, -t 18 -tb 36), (b) a saved greedy reference that later steps compare against, with a run-to-run identity check, (c) whether follow-up requests reuse the cached prompt on this hybrid model (the biggest practical risk), (d) whether a saved slot file lets a restarted server skip re-reading a long prompt.
Preconditions (read-only):
 1) the NONE-ACTIVE check from the top of section C prints NONE-ACTIVE
 2) python3 ~/speed/scripts/cpu_test.py fn-stock-il --bin stock --numa il --make-ref fn-stock --tests speed,prefill,cache,slot --check -- -lm dio -lzm off -t 18 -tb 36 -lv 4 --slot-save-path /home/simon/speed/slots
    must end with: CHECK OK (nothing started)
Command:
 sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=160G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=10800 -p TimeoutStopSec=180 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py fn-stock-il --bin stock --numa il --make-ref fn-stock --tests speed,prefill,cache,slot -- -lm dio -lzm off -t 18 -tb 36 -lv 4 --slot-save-path /home/simon/speed/slots
Watch (every ~10 min): journalctl -u cpu-test -n 12 --no-pager -o cat | cut -c1-200
Done when: systemctl is-active cpu-test prints inactive (or unknown).
Read: D=$(ls -d ~/speed/results/cpu/fn-stock-il/2* | tail -1); grep -v '^command' $D/summary.txt
Takes: ~30-40 min (load 3-6 min, 3 prompts x 2 runs x 256 tokens, a ~5K-token prefill, 3 chat turns, a slot save and restore).
Expected: decode mean ~5-6 t/s (MEASURED llama-bench 5.60, Sep 25); prefill ~40-50 t/s; "reference re-run identical: 3/3 | saved as reference fn-stock"; Jarvis median during within 10% of before; prompt cache PASS with turn 2 and 3 processing well under 100 tokens.
PASS: re-run identical 3/3 AND reference saved AND Jarvis during >= 90% of before AND no STOPPED/ERROR line.
The slot line is a finding too: on this hybrid model the re-sent prompt may be re-read in full after a restore, because slot files hold the state at the end of the saved tokens and no checkpoints (ESTIMATE from the server code; this measures it). The prompt-cache line is a finding either way. FAIL there (turn 2 or 3 re-reads most of the prompt) means every follow-up request pays the full prefill (~50 s per 2,500 tokens): tell Simon before any adoption.
FAIL (re-run not identical): greedy decoding is not deterministic on this build; stop the plan and tell Simon, because every identity check below depends on it.
Undo: nothing to undo (results stay in ~/speed/results/cpu; the slot file ~/speed/slots/cpu_test_slot.bin is overwritten by each run; delete it only with Simon's yes).
save_finding(topic="speed-flashnext", finding="FN-3 stock il: decode _/_/_ mean _, prefill _, rerun _/3, cache turns _ (PASS/FAIL, ckpt _ MiB), slot save _ s / restore _ s / re-read _ tokens, load _ s, RSS _ GiB, nodes _, Jarvis _ -> _", source="~/speed/results/cpu/fn-stock-il/<time>/summary.txt")
```

```text
JARVIS STEP FN-4 of 13: MTP on both sockets (PR #28243 build), with its MTP-off control
Goal: measure MTP n-max 3 (shared-Q8 head) together with interleaving, and measure how close the first differing token is (near-tie gap). The control uses the SAME PR binary with MTP off.
Preconditions: NONE-ACTIVE check passes; ls ~/speed/results/cpu/refs/fn-stock.json lists the file (FN-3 PASS). If the benchmark session already ran "MTP + interleave", still run B: it adds the near-tie gap and the Jarvis probes.
Run A, wait until it ends, then B (C is optional). Same way to watch and read as FN-3.
 A) sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=160G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=10800 -p TimeoutStopSec=180 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py fn-pr-off --bin fnmtp --numa il --ref fn-stock --tests speed -- -lm dio -lzm off -t 18 -tb 36
 B) sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=160G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=10800 -p TimeoutStopSec=180 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py fn-pr-mtp3 --bin fnmtp --numa il --ref fn-stock --tests speed,prefill -- -lm dio -lzm off -t 18 -tb 36 -md /home/simon/models/Qwen3.8-Flash-Next-unsloth/MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf --spec-type draft-mtp --spec-draft-n-max 3
 C) only if B passes: the B command with label fn-pr-mtp3-tb24 and -tb 24 instead of -tb 36
Read: for L in fn-pr-off fn-pr-mtp3 fn-pr-mtp3-tb24; do D=$(ls -d ~/speed/results/cpu/$L/2* 2>/dev/null | tail -1); [ -n "$D" ] && echo "== $L" && grep -E '^(decode|vs ref|prefill|Jarvis|STOP|ERROR)' $D/summary.txt; done
Takes: A ~20 min, B ~25 min, C ~25 min.
Expected: A decode within 5% of FN-3 and IDENTICAL to the reference (the PR is 5 commits older than stock; if NEAR-TIE, note it). B decode mean ~1.4-1.6x A (MEASURED 1.57x on socket 1); each prompt IDENTICAL or NEAR-TIE (gap <= 0.10); draft acceptance ~0.7-0.9.
PASS: B mean >= 1.3 x A mean AND every B prompt IDENTICAL or NEAR-TIE AND Jarvis during >= 85% of before. C is kept only if C mean >= 1.05 x B mean and C prefill >= 0.9 x B prefill.
FAIL: any DIVERGED (gap above 0.10) means MTP changes answers at a clear token: tell Simon, do not adopt MTP.
Undo: nothing (test units only).
save_finding(topic="speed-flashnext", finding="FN-4 PR il: off _ (vs ref _), MTP3 _ (x_; vs ref _ gap _; acc _), prefill _, tb24 _; Jarvis _ -> PASS/FAIL", source="~/speed/results/cpu/fn-pr-*/<time>/summary.txt")
```

```text
JARVIS STEP FN-5 of 13: ik_llama.cpp server, without and with its MTP
Goal: the ik engine as a server (the benchmark session's llama-bench head-to-head measures kernels; this adds MTP, prompt cache, identity and Jarvis impact).
Preconditions (read-only):
 1) NONE-ACTIVE check passes, and FN-3 PASS (ls ~/speed/results/cpu/refs/fn-stock.json)
 2) the ik queue is finished: grep -c '^ik-fn' ~/bench/queue.done ~/bench/queue.failed   (the two counts add up to 11, the job count of docs/bench/queue-ik.txt on Sep 25; if that queue changed, ask Simon)
 3) ~/ik_llama.cpp/build/bin/llama-server --help 2>&1 | grep -c -E 'spec-ckpt-mode|--no-mmap|run-time-repack'   (3 or more)
 4) python3 ~/bench/summary.py ~/bench/results/ik-fn-a2-rtr/*.json* 2>/dev/null | tail -4
    If the rtr=1 rows beat rtr=0 on both t/s columns, add -rtr to A and B below and put "-rtr" in the labels.
Run A, wait for it to end, then B:
 A) sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=160G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=10800 -p TimeoutStopSec=180 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py fn-ik --bin ik --numa il --ref fn-stock --tests speed,prefill,cache -- --no-mmap -t 18 -tb 36
 B) sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=160G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=10800 -p TimeoutStopSec=180 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py fn-ik-mtp3 --bin ik --numa il --ref fn-stock --tests speed,prefill -- --no-mmap -t 18 -tb 36 -md /home/simon/models/Qwen3.8-Flash-Next-unsloth/MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf --spec-type mtp:n_max=3 --spec-ckpt-mode per-step
Read: for L in fn-ik fn-ik-mtp3 fn-ik-rtr fn-ik-rtr-mtp3; do D=$(ls -d ~/speed/results/cpu/$L/2* 2>/dev/null | tail -1); [ -n "$D" ] && echo "== $L" && grep -E '^(decode|vs ref|prefill|prompt cache|Jarvis|STOP|ERROR)' $D/summary.txt; done
If B did not start: D=$(ls -d ~/speed/results/cpu/fn-ik-mtp3/2* | tail -1); tail -4 $D/server.log | cut -c1-200
Takes: ~30 min each.
Expected (ESTIMATE): A decode 1.0-1.2x FN-3, prefill 1.2-2x FN-3; each prompt IDENTICAL or NEAR-TIE (different kernels). ik prints no checkpoint lines, so judge its cache line by the token counts only. B mean >= 1.3x A.
PASS A: (decode >= 1.05 x FN-3 OR prefill >= 1.2 x FN-3) AND every prompt IDENTICAL or NEAR-TIE AND Jarvis during >= 90% of before.
PASS B: B mean >= 1.3 x A mean AND every prompt IDENTICAL or NEAR-TIE. The faster of FN-4 B and FN-5 B is the MTP candidate.
FAIL: DIVERGED anywhere -> not adoptable under the quality rule; record the gap and tell Simon.
Undo: nothing (test units only).
save_finding(topic="speed-flashnext", finding="FN-5 ik il: decode _ (x_ vs FN-3), prefill _ (x_), vs ref _, cache _; ik MTP3 _ (x_ vs A, acc _, vs ref _); rtr used: _ -> PASS/FAIL", source="~/speed/results/cpu/fn-ik*/<time>/summary.txt")
```

```text
JARVIS STEP FN-6 of 13: NUMA placement with the stock build (no fork)
Goal: A) interleaved memory plus --numa distribute (threads spread and pinned per node); B) first-touch placement: page cache emptied for the model files, mmap, no weight repacking, --numa distribute, so each page lands on the node whose threads read it. B uses -t 36 -tb 36 on purpose: pages are first touched by the batch threads (warm-up and prefill), and decode reads them locally only if it splits the rows the same way (ggml pins thread i to node i mod 2 and splits rows by thread under --numa). C (optional) separates the cost of --no-repack from the placement effect.
Preconditions (read-only):
 1) NONE-ACTIVE check passes; FN-3 PASS
 2) grep -l Qwen3.8-Flash-Next /proc/[0-9]*/maps 2>/dev/null | wc -l    must print 0 (nothing has the model mapped, so the eviction in B can work)
Run one at a time:
 A) sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=160G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=10800 -p TimeoutStopSec=180 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py fn-il-distr --bin stock --numa il --ref fn-stock --tests speed,prefill -- -lm dio -lzm off -t 18 -tb 36 --numa distribute
 B) sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=160G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=10800 -p TimeoutStopSec=180 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py fn-ft-distr --bin stock --numa none --evict --warm 3 --ref fn-stock --tests speed,prefill -- -lm mmap -lzm off --no-repack -t 36 -tb 36 --numa distribute
 C) only if B is slower than FN-3: the A command with label fn-il-norepack, and --no-repack instead of --numa distribute
Read: for L in fn-il-distr fn-ft-distr fn-il-norepack; do D=$(ls -d ~/speed/results/cpu/$L/2* 2>/dev/null | tail -1); [ -n "$D" ] && echo "== $L" && grep -E '^(load|decode|vs ref|prefill|Jarvis|STOP|ERROR)' $D/summary.txt; done
Takes: ~25 min each (B loads from disk after the eviction: a few minutes longer).
Expected: A within 5% of FN-3 (ESTIMATE). B: the "load" line shows evict [N, ~0] GiB and per-node MB roughly equal on both nodes; decode ESTIMATE -5% to +20% vs FN-3 (SOURCE both ways: PR #27986 author measured distribute = mirror at steady state on EPYC; the ik PR #2396 Broadwell test had distribute 2% below numactl).
PASS: decode >= 1.1 x FN-3 AND prefill >= 0.9 x FN-3 AND every prompt IDENTICAL or NEAR-TIE. Otherwise keep numactl --interleave=all.
Undo: nothing (the page cache refills on the next load).
save_finding(topic="speed-flashnext", finding="FN-6 numa: il+distribute _ (x_), first-touch _ (x_, prefill x_, nodes _), no-repack control _ -> keep _", source="~/speed/results/cpu/fn-*distr*/<time>/summary.txt")
```

```text
JARVIS STEP FN-7 of 13: build the ik NUMA-mirror test tree (~/ik-mirror)
Goal: ik PR #2396 ("NUMA Mirror implementation", open) merged onto the same ik commit the box already runs (1aaf7105), CPU-only, in its own new folder. The production llama.cpp and ~/ik_llama.cpp are not touched.
Preconditions (read-only):
 1) NONE-ACTIVE check passes
 2) ls -d ~/ik-mirror 2>&1 | tail -1     must say "No such file or directory"
 3) df -h --output=avail /home | tail -1   at least 5G
Commands:
 1) git clone -q --filter=blob:none https://github.com/ikawrakow/ik_llama.cpp ~/ik-mirror && git -C ~/ik-mirror checkout -q 1aaf7105be6e55a97fa4a9fd6f5bd362b08436dc && git -C ~/ik-mirror fetch -q origin pull/2396/head && git -C ~/ik-mirror log -1 --format='%h %ad %s' --date=short FETCH_HEAD
    Expected: 1efab5e5 2026-09-02 revert syntax format   (another hash means the PR moved on: continue, but record it)
 2) git -C ~/ik-mirror -c user.name=simon -c user.email=simon@localhost merge --no-commit --no-ff FETCH_HEAD 2>&1 | tail -2; git -C ~/ik-mirror diff --cached --shortstat
    Expected: "Automatic merge went well; stopped before committing as requested" and one "files changed" line. Any CONFLICT line: stop, tell Claude.
 3) sudo systemd-run --unit=build-ikmirror -p User=simon -p Group=simon -p Nice=10 -p WorkingDirectory=/home/simon/ik-mirror /bin/bash -c 'cmake -S . -B build -DGGML_NATIVE=ON -DGGML_CUDA=OFF -DCMAKE_BUILD_TYPE=Release >cfg.log 2>&1 && cmake --build build -j 36 --target llama-server >build.log 2>&1'
 4) when systemctl is-active build-ikmirror prints inactive or failed: tail -2 ~/ik-mirror/build.log | cut -c1-200; ~/ik-mirror/build/bin/llama-server --help 2>&1 | grep -c mirror
Takes: clone 1-5 min (history without file contents; files download as needed), build ~20-40 min.
Expected: "[100%] Built target llama-server" and a count of 1 or more.
PASS: the binary exists and its help mentions mirror. FAIL: tail -20 ~/ik-mirror/build.log | cut -c1-200, then tell Claude; clear a failed unit with sudo systemctl reset-failed build-ikmirror.
Undo: rm -rf ~/ik-mirror (Simon's yes).
save_finding(topic="speed-flashnext", finding="FN-7 ik-mirror built: PR head _, merge clean _, build ok _", source="~/ik-mirror/build.log")
```

```text
JARVIS STEP FN-8 of 13: NUMA mirror test (a weight copy on each socket)
Goal: measure ik --numa mirror beside Jarvis at 36 and 18 threads; then with MTP if both earlier MTP and mirror pass.
Preconditions (read-only):
 1) NONE-ACTIVE check passes; FN-7 PASS
 2) grep MemAvailable /proc/meminfo    at least 240,000,000 kB (the mirror needs ~2 x 104 GiB)
 3) cat /proc/sys/kernel/numa_balancing    0
Run one at a time (the mirror needs mmap, so never add --no-mmap here):
 A) sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=260G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=10800 -p TimeoutStopSec=180 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py fn-mirror36 --bin ikmirror --numa none --ref fn-stock --tests speed,prefill -- -t 36 -tb 36 --numa mirror
 B) the A command with label fn-mirror18 and -t 18 instead of -t 36
 C) only if A or B passes AND FN-5 B passed: the better of A/B with label fn-mirror-mtp3, adding: -md /home/simon/models/Qwen3.8-Flash-Next-unsloth/MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf --spec-type mtp:n_max=3 --spec-ckpt-mode per-step
Read: for L in fn-mirror36 fn-mirror18 fn-mirror-mtp3; do D=$(ls -d ~/speed/results/cpu/$L/2* 2>/dev/null | tail -1); [ -n "$D" ] && echo "== $L" && grep -E '^(load|decode|vs ref|prefill|Jarvis|STOP|ERROR)' $D/summary.txt; done
Takes: ~30 min each.
Expected: per-node MB about 100,000+ on each node; decode ESTIMATE 6.4-8 t/s (SOURCE ik PR #2396: +15% over numactl on 2x Broadwell with this model; ceiling ~7.5-10, section A); Jarvis impact similar to interleaving (-3% median MEASURED).
PASS: decode >= 1.1 x the better of FN-3 and FN-5 A AND every prompt IDENTICAL or NEAR-TIE AND Jarvis during >= 90% of before.
FAIL: keep the FN-3/FN-5 winner. A mirror run that stops with an error: tail -4 of its server.log, tell Claude.
Undo: nothing (test units only).
save_finding(topic="speed-flashnext", finding="FN-8 mirror: t36 _ , t18 _ (x_ vs best non-mirror _), prefill _, nodes _, vs ref _, Jarvis _; mirror+MTP _ -> PASS/FAIL", source="~/speed/results/cpu/fn-mirror*/<time>/summary.txt")
```

```text
JARVIS STEP FN-9 of 13: OPTIONAL lossy lever - GSQ-RCO IQ3_XXS: speed, then the KL-divergence gate
Goal: measure what the smaller quant would gain, then test it against the quality gate. Expected result: it FAILS the gate (ESTIMATE: Unsloth's table for this model has UD-IQ3_XXS at mean KLD 0.165 vs BF16, 3.5x UD-Q4_K_XL's 0.047).
Preconditions: NONE-ACTIVE check passes; FN-2 found the IQ3_XXS file (write its full path where it says IQ3PATH below); df -h --output=avail /home shows at least 15G.
Part A, speed (~30 min; the vs-reference lines will say DIVERGED because it is a different quant, ignore them here):
 sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=160G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=10800 -p TimeoutStopSec=180 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py fn-iq3 --bin stock --model IQ3PATH --numa il --ref fn-stock --tests speed,prefill -- -lzm off -t 18 -tb 36
 Read: D=$(ls -d ~/speed/results/cpu/fn-iq3/2* | tail -1); grep -E '^(load|decode|prefill|Jarvis|STOP|ERROR)' $D/summary.txt
Part B, KLD gate (~35 min, beside Jarvis, CPU only):
 1) cd ~/speed && ([ -f wikitext-2-raw/wiki.test.raw ] || (curl -sfL -o wt2.zip https://huggingface.co/datasets/ggml-org/ci/resolve/main/wikitext-2-raw-v1.zip && python3 -m zipfile -e wt2.zip . && rm wt2.zip)); ls -l wikitext-2-raw/wiki.test.raw
 2) sudo systemd-run --unit=kld-fn --collect -p User=simon -p Group=simon -p MemoryMax=200G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p WorkingDirectory=/home/simon/speed -E CUDA_VISIBLE_DEVICES= /bin/bash -c 'P="/usr/bin/numactl --interleave=all /home/simon/llama.cpp/build/bin/llama-perplexity"; W=wikitext-2-raw/wiki.test.raw; $P -m /home/simon/models/Qwen3.8-Flash-Next-unsloth/UD-Q4_K_XL/Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf -f $W -c 512 --chunks 40 -t 36 -lm dio -lzm off --kl-divergence-base kld/fn-q4.kld >kld/fn-base.log 2>&1 && $P -m IQ3PATH -f $W -c 512 --chunks 40 -t 36 -lzm off --kl-divergence-base kld/fn-q4.kld --kl-divergence >kld/fn-iq3.log 2>&1'
 3) when systemctl is-active kld-fn no longer prints active: grep -iE 'mean +kld|same top' ~/speed/kld/fn-iq3.log | head -4
PASS (the gate): "Same top p" >= 99% AND "Mean KLD" <= 0.01. Only then may Simon consider IQ3_XXS, and adoption still needs equal scores on his quality suite. FAIL: keep UD-Q4_K_XL.
Undo: rm ~/speed/kld/fn-q4.kld (ESTIMATE ~5 GB: 40 chunks x 255 scored tokens x ~248K vocab x 2 bytes; Simon's yes).
save_finding(topic="speed-flashnext", finding="FN-9 IQ3_XXS: decode _ (x_ vs FN-3), prefill _; gate same-top _%, mean KLD _ -> PASS/FAIL", source="~/speed/kld/fn-iq3.log")
```

```text
JARVIS STEP FN-10 of 13: SIMON ONLY - Jarvis must not run this. Transparent huge pages "always", A/B
Why SIMON ONLY: it changes a kernel setting for the whole box (every process, including Jarvis and Open WebUI), outside the test folders.
Goal: does llama.cpp decode faster when its 104 GiB weight buffer uses 2 MiB pages? (mainline never asks for huge pages itself; the box is on madvise.)
Preconditions (read-only): NONE-ACTIVE check passes; curl -s localhost:8080/health prints ok; cat /sys/kernel/mm/transparent_hugepage/enabled shows [madvise].
Commands:
 1) sudo systemd-run --unit=bench-fn-thp0 --collect -p User=simon -p Group=simon -p MemoryMax=160G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -E CUDA_VISIBLE_DEVICES= -p StandardOutput=file:/home/simon/speed/results/fn-thp0.jsonl /usr/bin/numactl --interleave=all /home/simon/llama.cpp/build/bin/llama-bench -m /home/simon/models/Qwen3.8-Flash-Next-unsloth/UD-Q4_K_XL/Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf -lm dio -lzm off -t 18 -p 512 -n 128 -r 3 -o jsonl
 2) when systemctl is-active bench-fn-thp0 no longer prints active: echo always | sudo tee /sys/kernel/mm/transparent_hugepage/enabled
 3) command 1 again with thp1 in both the unit name and the output file name; while it runs: grep AnonHugePages /proc/meminfo (should climb towards ~100 GB)
 4) ALWAYS, even if 3 failed: echo madvise | sudo tee /sys/kernel/mm/transparent_hugepage/enabled
Read: python3 ~/bench/summary.py ~/speed/results/fn-thp0.jsonl ~/speed/results/fn-thp1.jsonl
Takes: 2 x ~8 min.
PASS: tg128 with "always" >= 1.03 x madvise (run-to-run noise here is ~2%, MEASURED Sep 25). Keeping "always" permanently is a separate decision for Simon; ik's per-process -thp flag is the alternative that changes nothing else.
Undo: command 4.
save_finding(topic="speed-flashnext", finding="FN-10 THP: madvise tg _ pp _, always tg _ pp _ -> PASS/FAIL", source="~/speed/results/fn-thp*.jsonl")
```

```text
JARVIS STEP FN-11 of 13: SIMON ONLY - Jarvis must not run this. OPTIONAL: what one whole V100 is worth to Flash-Next
Why SIMON ONLY: it needs a GPU, so Jarvis must be off; the benchmark runner stops and restarts Jarvis for "gpu" jobs in the 1-7 AM window.
Goal: informational, for the "Jarvis on one card" idea: all non-expert tensors on GPU0, all routed experts on CPU, and big-batch prefill where the GPU does the expert matmuls (weights copied over PCIe once per 4,096-token batch).
Preconditions (read-only):
 1) systemctl is-active bench-queue prints inactive (never edit the queue while the runner runs)
 2) from FN-2: "everything else" is at most 11 GB (it must fit a 16 GB card with room for buffers)
Do: add this line to ~/bench/queue.txt, then start the runner in the night window the usual way (HANDOFF):
 fn-g1-hybrid gpu 2 -m /home/simon/models/Qwen3.8-Flash-Next-unsloth/UD-Q4_K_XL/Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf -lm dio -lzm off -dev CUDA0 -ngl 99 -ncmoe 48 -t 18 -b 4096 -ub 512,4096 -p 4096 -n 128 -r 1
Read (next morning): python3 ~/bench/summary.py ~/bench/results/fn-g1-hybrid/*.jsonl
Takes: ~30-60 min inside the night window.
Expected (ESTIMATE): decode 8-10 t/s (only the routed experts stay on the CPU side; FN-2 gives their share), prefill at ub 4096 ~200-500 t/s, at ub 512 about CPU speed. Compare with the Jarvis-off CPU-only job fn-b1-interleave when it has run.
PASS/FAIL: none; this is a number for Simon's decision. Undo: delete the line from ~/bench/queue.txt (a finished label is skipped anyway).
save_finding(topic="speed-flashnext", finding="FN-11 one V100: tg _ , pp4096 at ub512 _ / ub4096 _ vs CPU-only _", source="~/bench/results/fn-g1-hybrid")
```

```text
JARVIS STEP FN-12 of 13: SIMON ONLY - Jarvis must not run this. Run Flash-Next as a service (port 8081)
Why SIMON ONLY: it creates a new production systemd unit and keeps ~104 GiB of RAM in use.
Preconditions (read-only): FN-3 PASS including the prompt-cache line; the chosen variant PASSED in its step (FN-4, FN-5, FN-6 or FN-8); NONE-ACTIVE check passes; grep MemAvailable /proc/meminfo at least 136,000,000 kB (240,000,000 for the mirror). The spare-port test for these exact flags is the harness run on port 8082 in that step.
Commands (Simon, in his terminal):
 1) sudo tee /etc/systemd/system/flash-next.service >/dev/null <<'UNIT_END'   then paste the unit text from section D (ExecStart swapped for the variant that won), then a line UNIT_END
 2) sudo systemctl daemon-reload && sudo systemctl start flash-next
 3) for i in $(seq 60); do curl -sf localhost:8081/health && break; sleep 10; done
 4) curl -s localhost:8081/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"Say OK."}],"max_tokens":300,"chat_template_kwargs":{"reasoning_effort":"low"}}' | python3 -c "import json,sys;r=json.load(sys.stdin);print(r['choices'][0]['message'].get('content'),r['timings']['predicted_per_second'])"
 5) curl -s localhost:8080/health    (Jarvis still answers)
 6) only when satisfied: sudo systemctl enable flash-next
Expected: 3 prints {"status":"ok"} within ~10 min; 4 prints an answer and a speed close to the winning step's decode mean.
PASS: 3, 4 and 5 all succeed. FAIL: rollback below, then journalctl -u flash-next -n 30 --no-pager.
Rollback: sudo systemctl disable --now flash-next && sudo mv /etc/systemd/system/flash-next.service ~/speed/flash-next.service.off && sudo systemctl daemon-reload
Notes: while flash-next runs, t27_window.py (27B tests, port 8081) refuses to start, and GLM/MiMo tests must not load (one big model at a time): sudo systemctl stop flash-next first.
save_finding(topic="speed-flashnext", finding="FN-12 flash-next service started with variant _, probe _ t/s, enabled _", source="systemctl status flash-next")
```

```text
JARVIS STEP FN-13 of 13: check the service after 48 hours of real use (read-only)
Goal: confirm the speed holds under real work and that follow-up requests reuse the prompt cache.
Precondition: FN-12 done at least 48 hours ago; systemctl is-active flash-next prints active.
Commands:
 1) journalctl -u flash-next --since "-48h" -o cat --no-pager | python3 ~/speed/scripts/j27_logstats.py
 2) journalctl -u flash-next --since "-48h" -o cat --no-pager | grep -c -E 'GGML_ASSERT|ggml_abort|out of memory|Segmentation'
 3) curl -s localhost:8080/health; echo; curl -s localhost:8081/health
Takes: 1 minute.
Expected: 1 prints decode and prompt-eval percentiles (j27_logstats.py reads mainline/PR log lines; for an ik service it may parse nothing: then read journalctl -u flash-next -n 30 instead); 2 prints 0; 3 prints two ok lines.
PASS: token-weighted decode >= 0.9 x the winning step's decode mean AND command 2 prints 0 AND the prompt-eval p50 is seconds, not minutes (the cache works). FAIL: tell Simon; rollback is in FN-12.
Undo: nothing (read-only).
save_finding(topic="speed-flashnext", finding="FN-13 after 48 h: decode p50 _ weighted _, prompt-eval p50 _ ms, requests re-reading >=8000 tokens _, crash lines _ -> PASS/FAIL", source="journalctl flash-next 48h")
```

## D. Proposed final config (PROPOSED until FN-3..FN-8 measure it)

Default = the best measured pieces (MTP 1.57x MEASURED on socket 1; interleaving +28% MEASURED): PR #28243 build, MTP n-max 3, both sockets interleaved. ESTIMATE ~8.8 t/s decode (5.60 x 1.57), ~50 t/s prefill, Jarvis ~-3% median while it generates.

```ini
[Unit]
Description=Flash-Next CPU worker (llama-server on 127.0.0.1:8081)
After=network-online.target llama-server.service

[Service]
User=simon
Group=simon
Environment=CUDA_VISIBLE_DEVICES=
ExecStart=/usr/bin/numactl --interleave=all /home/simon/llama.cpp-fnmtp/build/bin/llama-server -m /home/simon/models/Qwen3.8-Flash-Next-unsloth/UD-Q4_K_XL/Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf -lm dio -lzm off -t 18 -tb 36 -c 65536 --parallel 1 --jinja --host 127.0.0.1 --port 8081 -md /home/simon/models/Qwen3.8-Flash-Next-unsloth/MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf --spec-type draft-mtp --spec-draft-n-max 3
MemoryMax=180G
MemorySwapMax=0
OOMScoreAdjust=500
Nice=5
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Why these values: `-t 18 -tb 36` (MEASURED best decode and prefill thread counts interleaved); `-lm dio -lzm off` (as benchmarked: weights and the n-gram table resident, no page-cache surprises); `-c 65536` (decode loses 30% by 64K, MEASURED; filling 64K takes tens of minutes, so bigger is possible but slow; raise if Simon needs it); checkpoint settings left at their defaults unless FN-3's cache line fails; `--parallel 1` (one worker job at a time; ik MTP only allows 1); `Nice=5` so Jarvis's own CPU work wins any contention (ESTIMATE: trims the -15% worst-probe dips; not measured); `MemorySwapMax=0` so weights are never swapped.

Swap in the ExecStart of whichever variant wins:
- ik (FN-5): `ExecStart=/usr/bin/numactl --interleave=all /home/simon/ik_llama.cpp/build/bin/llama-server -m <same model> --no-mmap -t 18 -tb 36 -c 65536 --parallel 1 --jinja --host 127.0.0.1 --port 8081 -md <same head> --spec-type mtp:n_max=3 --spec-ckpt-mode per-step` (add `-rtr` if FN-5 used it).
- mirror (FN-8): `ExecStart=/home/simon/ik-mirror/build/bin/llama-server -m <same model> -t 36 -tb 36 --numa mirror -c 65536 --parallel 1 --jinja --host 127.0.0.1 --port 8081` plus the ik MTP flags if FN-8 C passed; set `MemoryMax=260G`. ESTIMATE 10-13 t/s with MTP (6.4-8 x 1.57).
- first-touch (FN-6 B): `ExecStart=/home/simon/llama.cpp-fnmtp/build/bin/llama-server -m <same model> -lm mmap -lzm off --no-repack --numa distribute -t 36 -tb 36 ...` (no numactl wrapper; keep -t equal to -tb, see FN-6).

## E. Open questions and VERIFY items (each with a read-only command)

1. Exact bytes per token and the routed-expert share: FN-2 command 2 (`gguf_bytes.py`). Every ESTIMATE in section A moves with it.
2. Does this model's chat template use `reasoning_effort`? FN-2 command 7 (count above 0 = yes). If not, the harness's effort settings are ignored and reasoning runs at the template default.
3. Is `~/ik_llama.cpp` a CUDA or CPU build? `grep -E '^GGML_CUDA:BOOL' ~/ik_llama.cpp/build/CMakeCache.txt` (with GPUs hidden either works; a CUDA build may print warnings).
4. Has PR #28243 moved past the box's 6fcaa16f4? Box: `git -C ~/llama.cpp-fnmtp log -1 --format='%h %ad' --date=short`. The PR page showed head 6fcaa16 on 2026-09-25 (SOURCE [PR #28243](https://github.com/ggml-org/llama.cpp/pull/28243)); maintainers asked for simplification, so it may change before merging.
5. KV and checkpoint memory at 64K: `D=$(ls -d ~/speed/results/cpu/fn-stock-il/2* | tail -1); grep -m4 -iE 'KV (self|buffer) size|recurrent|context checkpoint' $D/server.log | cut -c1-200` after FN-3.
6. Whether the model files are already in the page cache (warm reloads): `fincore --bytes ~/models/Qwen3.8-Flash-Next-unsloth/UD-Q4_K_XL/*.gguf | tail -5`.
7. BIOS: CPU v4 support and snoop mode. `sudo dmidecode -t bios | grep -E 'Version|Release Date'` (read-only); the snoop mode is only visible in the BIOS setup screen (Simon), and the v4 support needs ASUS's CPU support list for Z10PG-D16.
8. ik's `--spec-ckpt-mode per-step` on a CPU-only run: FN-5 B answers it; if it errors, the fallback modes re-decode on every rejection (slower).
9. Other engines: KTransformers and vLLM/SGLang CPU backends were not found to support qwen4exp; VERIFY on their repos before spending time (no box command).
10. The benchmark session's pending items that overlap: MTP + interleave (FN-4 covers it with the near-tie gap), shared-Q4 head at n-max 3 (not scheduled here; the MEASURED n-max 2 result was equal to shared-Q8), Jarvis-off interleave jobs fn-b1-* (baseline for FN-11).
