# Qwen3.8-Flash-Next on jarvis-1: plan, estimates, results

Model: unsloth UD-Q4_K_XL, 4 shards, 111,334,654,784 B (= 103.7 GiB; shard sizes on the NVMe add up to exactly the HF size, MEASURED 2026-09-25). 6B active, 48 layers (3 Gated DeltaNet : 1 QSA), 512 experts. Stock llama.cpp supports it (qwen4exp). Copy at /home/simon/models/Qwen3.8-Flash-Next-unsloth/ (UD-Q4_K_XL/, MTP/ with 6 draft files, mmproj-F16.gguf). NOT yet sha256-verified.
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
- PR's own known issues (web check 2026-09-25): --fit does not count MTP weights; greedy output diverges at n-max >= 3 on some hardware; low acceptance (~0.36-0.39) on some GPU setups; M-RoPE position errors in later testing. So every MTP run must also check greedy output is IDENTICAL with MTP off, not just speed.
- Vendor numbers (B200, greedy): 1.67x on UD-Q4_K_XL, acceptance ~66%. Net LOSS at concurrency 8 (0.81-0.87x). Speedup shrinks at higher temperature. CPU gain unmeasured.

## Test order
1. Day 1 llama-bench queue (docs/bench/queue-fn.txt): socket 1 beside Jarvis, then interleaved in the night window.
2. llama-server harness: MTP drafts (Q8_0 / Q4_K_M, shared vs plain) with --spec-type draft-mtp and n-max 1-5; --parallel 1/2/4/8; prompt-cache reuse with -lv 4 (Gated DeltaNet is HIGH RISK for forced full re-processing); max-context needle test.
3. NUMA mirror fork and ik_llama.cpp builds (separate trees).
4. GSQ-RCO IQ3_XXS and Q2_0 with the best flags; KL divergence vs UD-Q4_K_XL.

## Results
None yet.
