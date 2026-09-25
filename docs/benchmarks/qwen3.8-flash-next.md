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

## Test order
1. Day 1 llama-bench queue (docs/bench/queue-fn.txt): socket 1 beside Jarvis, then interleaved in the night window.
2. llama-server harness: MTP drafts (Q8_0 / Q4_K_M, shared vs plain) with --spec-type draft-mtp and n-max 1-5; --parallel 1/2/4/8; prompt-cache reuse with -lv 4 (Gated DeltaNet is HIGH RISK for forced full re-processing); max-context needle test.
3. NUMA mirror fork and ik_llama.cpp builds (separate trees).
4. GSQ-RCO IQ3_XXS and Q2_0 with the best flags; KL divergence vs UD-Q4_K_XL.

## Results
None yet.
