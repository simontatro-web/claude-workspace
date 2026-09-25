# Qwen3.8-Flash-Next on jarvis-1: plan, estimates, results

Model: unsloth UD-Q4_K_XL, 4 shards, 111,334,654,784 B (= 103.7 GiB; shard sizes on the NVMe add up to exactly the HF size, MEASURED 2026-09-25). 6B active, 48 layers (3 Gated DeltaNet : 1 QSA), 512 experts. Stock llama.cpp supports it (qwen4exp). Copy at /home/simon/models/Qwen3.8-Flash-Next-unsloth/ (UD-Q4_K_XL/, MTP/ with 6 draft files, mmproj-F16.gguf). sha256-VERIFIED 2026-09-25 12:33 PM CT (big-verify: 21 files, 338.8 GB, all match Hugging Face, together with GLM-5.3-Flash).
Also on the drive only: GSQ-RCO IQ3_XXS and Q2_0 (to load straight from /mnt/models/models; -lm dio on NTFS is VERIFY).

## Speed estimate, corrected 2026-09-25 (ESTIMATE, nothing measured yet)
The wiki (qwen38-flash-next) says ~10.5 t/s stock, ~14-17 mirrored, ~18-27 with MTP. That stacks three best cases and uses ~39 GB/s, which is a BOTH-socket figure.
Night 1 on GLM-5.3 measured llama.cpp reaching ~62% of STREAM. With ~3.7 GB read per token:
| setup | bandwidth basis | decode estimate |
|---|---|---|
| socket 1 only, beside Jarvis | 29.5 GB/s STREAM x 0.6-0.75 | ~5-6 t/s |
| interleaved, Jarvis off | ~37 GB/s effective | ~10 t/s |
| NUMA mirror fork | up to ~2x one socket | ~10-13 t/s |
| mirror + MTP (x1.3-1.6, VERIFY on CPU) | | ~13-19 t/s |
27 t/s is not a realistic target on this box unless measurement beats these numbers. The per-token byte count (3.7 GB) is itself an estimate; the day-1 baseline settles it.

## MTP draft heads (from MTP/README.md on the box, read 2026-09-25)
- Recommended: mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf. "shared-" heads borrow tok_embd and output from the main model; they need a build with borrowing support. Self-contained Q8_0/Q4_K_M/BF16 work without it.
- Must pass -md explicitly (auto-discovery does not look in MTP/). A shared head logs one borrow_shared_tensor error at startup from the memory-fit probe and then works; pass -c yourself.
- Confirm it runs: log line "draft acceptance = ... mean len = ...". Default --spec-draft-n-max 2.
- README claims stock mainline has no qwen4exp MTP graph, no borrowing and no --spec-type draft-mtp. Our build f4e276a20 DOES have --spec-type draft-mtp (production 27B uses it), so the README is at least partly out of date. Whether our build has the qwen4exp MTP graph and borrowing is VERIFY (grep the source). If not: build PR #28243 (branch danielhanchen/llama.cpp qwen4exp/mtp) in its own tree.
- CHECKED 2026-09-25: our build f4e276a20 has NO borrow_shared_tensor and no qwen4exp MTP/nextn code (grep empty), and no commit mentioning 28243. PR #28243 "models: Qwen3.8-Flash-Next MTP" (danielhanchen, head qwen4exp/mtp) is still OPEN. So MTP for Flash-Next needs a PR build in a separate worktree (~/llama.cpp-fnmtp).
- FETCHED 2026-09-25 as a git worktree: ~/llama.cpp-fnmtp at PR commit 6fcaa16f4 ("Address review comments"), branch pr-28243 in ~/llama.cpp. Download was 155 KiB. Production ~/llama.cpp still at f4e276a20 (MEASURED). BUILT 2026-09-25 12:16 PM CT (build-fnmtp, CPU-only, numactl socket 1, 18 min CPU): ~/llama.cpp-fnmtp/build/bin/{llama-server,llama-bench,llama-cli}. Shared-library build: binaries use the libs in the same build/bin. PR base bb3c853c3 (2026-09-21), only 5 commits behind production f4e276a20 (MEASURED); -lm/-lzm present, no --no-mmap. Worktree 174M.
- Control rule: MTP on/off comparisons are run with the SAME PR binary, never PR-with-MTP vs stock-without.
- PR's own known issues (web check 2026-09-25): --fit does not count MTP weights; greedy output diverges at n-max >= 3 on some hardware; low acceptance (~0.36-0.39) on some GPU setups; M-RoPE position errors in later testing. So every MTP run must also check greedy output is IDENTICAL with MTP off, not just speed.
- Vendor numbers (B200, greedy): 1.67x on UD-Q4_K_XL, acceptance ~66%. Net LOSS at concurrency 8 (0.81-0.87x). Speedup shrinks at higher temperature. CPU gain unmeasured.

## Test order
1. Day 1 llama-bench queue (docs/bench/queue-fn.txt): socket 1 beside Jarvis, then interleaved in the night window.
2. llama-server harness: MTP drafts (Q8_0 / Q4_K_M, shared vs plain) with --spec-type draft-mtp and n-max 1-5; --parallel 1/2/4/8; prompt-cache reuse with -lv 4 (Gated DeltaNet is HIGH RISK for forced full re-processing); max-context needle test.
3. NUMA mirror fork and ik_llama.cpp builds (separate trees).
4. GSQ-RCO IQ3_XXS and Q2_0 with the best flags; KL divergence vs UD-Q4_K_XL.

## Results
### fn-a0-baseline (socket 1 only, beside Jarvis, 18 threads, -r 3) - MEASURED 2026-09-25 12:42 PM CT
| test | t/s |
|---|---|
| prefill pp512 | 29.35 |
| decode tg128 | **4.10** |
Below the 5-6 t/s estimate. 4.10 t/s x ~3.7 GB/token (ESTIMATE) = ~15 GB/s, about 51% of socket-1 STREAM (29.5 GB/s); either llama.cpp reaches less of the bandwidth on this model or it reads more bytes per token than estimated. Still ~3.7x GLM-5.3's 1.11 t/s beside Jarvis. Load + 3 reps took 5 min.

### Day-1 flag sweep (socket 1 only, beside Jarvis) - MEASURED 2026-09-25 12:42-4:19 PM CT
Threads (fn-a1):
| threads | 9 | 12 | 16 | 18 | 36 |
|---|---|---|---|---|---|
| prefill pp512 | 16.94 | 22.01 | 28.01 | 29.35 | **31.67** |
| decode tg128 | **4.38** | 4.32 | 4.19 | 4.17 | 3.93 |
FEWER threads decode FASTER (9 beats 18 by 5%): decode is bandwidth-bound and extra threads add contention. Prefill wants all 36 hyperthreads (+8% over 18). So in llama-server use -t ~9-12 for decode and -tb 36 for prefill. 6/8/10 not yet tried.
Prompt batch (fn-a2, pp4096, 18 threads): ubatch 512 27.79 / 1024 26.59 / 2048 26.28 / 4096 25.34. Default 512 is best; bigger is slower here.
Hyperthreads for a 4K prompt (fn-a2b): 18 threads 26.22, 36 threads 28.84 (+10%).
Flash attention (fn-a3): depth 0 identical; at 8K depth decode 4.01 on vs 3.88 off (+3%), prefill 23.25 on vs 24.31 off (-4%). Near neutral; on for decode-heavy use.
8-bit K/V cache (fn-a5, fa on): 29.03 / 4.16 at depth 0, 24.47 / 3.98 at 8K: no speed cost vs f16. Halves cache RAM; quality effect not measured.
Depth (fn-a6, 18 threads, fa auto):
| depth | 0 | 16K | 32K | 64K |
|---|---|---|---|---|
| prefill pp512 | 29.35 | 20.60 | 16.20 | 10.66 |
| decode tg128 | 4.17 | 3.87 | 3.58 | 2.91 |
Decode loses only 30% by 64K (GLM-5.3 lost 33% by 16K). Filling a 64K prompt takes ~70 min on socket 1 (the 64K job took 77 min including load); 16K ~11 min. Long context is practical on this model, slowly.
Best single-socket stock config so far: -t 9-12 (decode) -tb 36 (prefill), -ub 512, -fa on, K/V q8_0 optional.

## Commands kept for later
Build the MTP PR (only after "Benchmark queue finished"; CPU-only; production untouched):
```
sudo systemd-run --unit=build-fnmtp -p User=simon -p Group=simon -p WorkingDirectory=/home/simon/llama.cpp-fnmtp /bin/bash -c 'cmake -S . -B build -DGGML_CUDA=OFF -DGGML_NATIVE=ON -DCMAKE_BUILD_TYPE=Release && cmake --build build -j 36 --target llama-server llama-bench llama-cli'
journalctl -u build-fnmtp -n 5 --no-pager
```
