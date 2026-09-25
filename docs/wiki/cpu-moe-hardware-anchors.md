# cpu-moe-hardware-anchors

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 23, 2026).
> Cowork-only links kept as page names.
>
> Summary: Real measured throughput from hardware comparable to jarvis-1 (dual Xeon E5 v4, DDR4) on large MoE models, the working ik_llama.cpp flag set from that run, and the GSQ-RCO quant family that beats the bits-per-weight/quality curve. Read before choosing flags or quants for any big CPU-resident model. Split out of [[cpu-moe-speed-levers]], which hit its 48 KB cap Sep 23 2026.

Companions: cpu-moe-speed-levers (the ranked levers), model-download-manifest (what to pull), context-and-speed-per-model, system-performance-levers.

## *** THE CLOSEST HARDWARE ANALOG ANYONE HAS PUBLISHED [SOURCE: ubergarm/GLM-4.7-GGUF discussion #5, read live Sep 23 2026] ***

Hardware: 2x Xeon E5-2696 v4 (Broadwell, 22 physical cores each, NO AVX-512), 460 GB DDR4-2400, 2x RTX 5090, Dell T630, bare metal. One CPU generation newer than Jack's Haswell E5-2699 v3, faster memory (2400 vs his 1866), same AVX2-only ceiling, same dual-socket DDR4 topology. Best real-world anchor on file for what a big GLM-class MoE does on this class of machine. | quant | context | token generation | prompt processing | | IQ4_K | 84,992 | ~6.1 t/s | ~16.4 t/s | | IQ5_K | 102,400 | ~4.8-5.1 t/s | ~14.3 t/s, or ~44 t/s with graph mode |

### THE WORKING ik_llama.cpp FLAG SET FROM THAT RUN — several are new to this memory

```bash
--threads 44 --threads-batch 88 --batch-size 2880 --ubatch-size 576
--split-mode graph --tensor-split 48,52 --numa distribute
--run-time-repack -gr -ger --merge-qkv
--cache-type-k q4_0 --cache-type-v q4_0 --k-cache-hadamard
```

*** THE FINDING WORTH TAKING: --threads AND --threads-batch SHOULD DIFFER. *** Their stated conclusion: "physical cores dominate generation speed while hyperthreading maximizes prompt processing." For Jack that is --threads 36 --threads-batch 72. This REFINES, not contradicts, the "physical cores only, never 72" rule in system-performance-levers (derived from STREAM, where 36 threads socket-local scored slightly BELOW 18). That rule is right for DECODE, which is bandwidth-bound and gains nothing from hyperthreading. It is wrong for PREFILL, which is compute-bound and does. Two regimes, two thread counts.

### OTHER FLAGS TO INVESTIGATE, all new here

- --split-mode graph — appears to be what turns 14.3 t/s prefill into ~44 t/s. Highest-value unknown on this list.
- --merge-qkv — *** directly relevant to ik_llama issue #1769, where MiMo V2.5 Pro GGUFs fail to load with tensor 'blk.0.attn_q.weight' not found because of fused QKV. This flag may be the workaround that brings the ik_llama engine lever to MiMo. ***
- --k-cache-hadamard — a Hadamard transform on the K cache, the same idea underlying TurboQuant, used here alongside q4_0 K and V.
- -gr / -ger — undocumented here; check --help on the built binary.
- --run-time-repack (-rtr) — already covered in model-pull-and-flags; note it disables mmap and needs RAM for the whole repacked model.

### *** SOBERING, AND IT CONFIRMS THE PREFILL WARNING: PROMPT PROCESSING IS ONLY 16-44 t/s ON BETTER HARDWARE THAN JACK'S ***

At 16.4 t/s a 32K prompt is 33 minutes to first token. Prefill, not decode, is what will make these models painful. Treat --split-mode graph, --threads-batch and -b/-ub as first-class levers, not nice-to-haves.

### CALIBRATION FOR JACK: EXPECT BELOW THESE FIGURES

DDR4-1866 vs their 2400 is ~22% less theoretical bandwidth, and Haswell costs a little more than Broadwell. Scaling the 6.1 t/s IQ4_K result lands near 4.5-5 t/s for a comparable GLM-class MoE — consistent with the 2.5-5 t/s stacked projection in cpu-moe-speed-levers. Not measured on Jack's box.

## *** GSQ-RCO — A QUANT FAMILY THAT BEATS THE bpw/QUALITY CURVE, AND IT IS A DOWNLOAD-TIME DECISION ***

ISTA-DASLab = IST Austria Distributed Algorithms and Systems Lab, the group behind GPTQ, QuIP, AQLM and HIGGS. Not a community repacker.

- GSQ = Gumbel-Softmax post-training scalar quantization (learns per-coordinate grid assignments and per-group scales).
- RCO = Riemannian Constrained Optimization, assigning a quant type per tensor against a total size budget.
- Code: github.com/IST-DASLab/GSQ. *** Runs unmodified on mainline llama.cpp — no special build. *** Qwen3.8-Flash-Next: IQ3_XXS is 3.00 bpw / 70.63 GiB versus unsloth UD-Q4_K_XL at 4.95 bpw / 103.69 GiB. Decode is bytes-per-token bound, so that is a ~65% decode gain (~9.9 -> ~16.3 t/s at the measured 36.6 GB/s), and 70.63 GiB is far enough inside one socket that NUMA mirroring is trivial, stacking toward ~24 t/s before MTP. Claimed quality [VENDOR, but with published plots]: 99.4% of baseline task average, AIME25 unchanged at 100.00, at 4.7x smaller than BF16. The repo ships per-benchmark recovery plots (aime25, gpqa_diamond, lcb, ppl on c4/fineweb-edu/wikitext2, task_avg, zero-shot) — check those before trusting the headline. *** WHY THIS IS URGENT RATHER THAN INTERESTING: it is a lever of the same magnitude as the engine swap or NUMA mirroring, but unlike those it CANNOT be applied after the fact. It is a different file that has to be downloaded on the trip. *** Exact sizes and the take-both recommendation are in model-download-manifest. Coverage checked Sep 23 2026: available for Qwen3.8-Flash-Next and Qwen3.8-27B (the 27B without MTP, which makes it the wrong pick for Jack's GPU slots); community GSQ-RCO exists for GLM-5.3-Flash (taurusduan/, pfeifferj/); NONE for GLM-5.3 full, Hy4-preview or MiMo-V2.6.
