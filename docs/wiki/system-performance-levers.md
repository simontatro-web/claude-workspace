# system-performance-levers

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 23, 2026).
> Cowork-only links kept as page names.
>
> Summary: Whole-system performance work for jarvis-1 beyond model choice (Sep 23 2026) — the memory-bandwidth investigation that multiplies every model's speed, the multimodal cost/benefit per slot, and other system-wide improvements. Read when asking "how do I make the whole thing better", not just "which model".

Companions: cpu-moe-speed-levers (per-model speed), context-and-speed-per-model, v100-speed-frontier (GPU), gpu-upgrade-options, model-pull-and-flags.

## *** LEVER #1, AND IT IS BIGGER THAN ANY MODEL CHOICE: THE 39 GB/s FIGURE MAY BE LEAVING 30-50% ON THE TABLE, AND NOBODY HAS CHECKED. ***

Every decode-speed number in this memory is `effective bandwidth ÷ bytes-per-token`, and they all use ~39 GB/s. That constant is load-bearing for the entire model plan, and its provenance is not recorded. If it is wrong or improvable, EVERY model gets faster in direct proportion. A 1.5x bandwidth gain is worth more than any model swap on the list. THE THEORETICAL NUMBERS (Intel spec: E5-2699 v3 = 4 DDR4 channels per socket, max DDR4-2133): | DIMM speed | Per channel | Per socket (4ch) | Dual-socket (8ch) | | DDR4-2133 | 17.06 GB/s | 68.3 | 136.5 | | DDR4-1866 | 14.93 GB/s | 59.7 | 119.5 | | DDR4-1600 | 12.80 GB/s | 51.2 | 102.4 | cpu-moe-speed-levers records the box as "DDR4-1866". So single-socket theoretical is ~59.7 GB/s. Measured 39 GB/s is 65% of that — plausible for a STREAM-style single-socket result. But if 39 was meant as the DUAL-socket figure it is only 33% of 119.5, which would indicate a real misconfiguration. *** THE QUESTION THAT DECIDES IT: was 39 GB/s measured single-socket or interleaved across both? *** COMMANDS TO SETTLE THIS — do these before any further model tuning:

```bash
sudo dmidecode -t memory | grep -E "Size|Speed|Configured|Locator|Rank|Type:" | head -80
#   -> actual configured speed vs rated speed, DIMM count, which channels are populated
lscpu | grep -i numa
numactl --hardware
sudo apt install -y mbw
mbw -n 5 4096                                   # rough single-thread
numactl --cpunodebind=0 --membind=0 mbw -n 5 4096   # socket 0 local
numactl --interleave=all mbw -n 5 4096              # both sockets interleaved
```

WHAT GOOD LOOKS LIKE: socket-local should land near 40-50 GB/s at 1866; interleaved should be meaningfully higher than socket-local. If `Configured Memory Speed` reads 1600 while the DIMMs are rated 2133, that is a BIOS setting and a free ~33% on every model. THE HARDWARE PATH IF IT IS CAPPED BY POPULATION: 16 DIMMs across 8 channels is 2 DIMMs per channel, which is exactly the configuration that forces Haswell-EP down from 2133 to 1866. Going to 8 x 64 GB at 1 DIMM per channel would keep 512 GB, restore 2133, gain ~14% bandwidth on everything, and free 8 slots. Costs money; price it before committing. Counter-warning already on file in mimo-v2.6-feasibility: quad-rank 64 GB LRDIMMs in all 16 slots commonly drop to 1600, which would LOSE ~25%. The win only exists at 1 DIMM per channel.

## LEVER #2 — MULTIMODAL, SLOT BY SLOT (Jack asked what difference it makes for each)

File costs, verified from the HF APIs: Flash-Next `mmproj-F16.gguf` 904,004,000 B (0.90 GB) / `mmproj-BF16.gguf` 907,542,944 B. GLM-5.3-Flash mmproj F16 1.13 GB / BF16 1.16 GB. Uncensored 27B mmproj Q8_0 629,247,648 B (0.63 GB). GLM-5.3 full ships NO mmproj — checked, the repo root has no mmproj file, so that slot is text-only regardless. *** THE REAL COST IS NOT THE FILE, IT IS VRAM WORKSPACE. *** orchestrator-slot-plan measured it: the vision tower makes the CLIP graph materialize a 4.27 GiB attention matrix because flash attention is compiled out, and that 4.8 GiB card imbalance is the reason a single-card 27B layout looked impossible. Dropping mmproj is what frees the second V100. *** BUT THAT MAY NOW BE FIXABLE: `fishlikeX/sm70-attn` brings flash attention to sm_70. With FA present the 4.27 GiB workspace should collapse, which would make vision affordable on the GPU slots again. UNTESTED — this is a real experiment worth running. *** Value per slot, against Jack's stated uses (agentic building, tutoring content, deep research, websites, self-improvement): | Slot | Worth vision? | Why | | 27B judge / interactive | YES, highest value | Screenshot the rendered page, let it see its own output and iterate. Directly serves "build very good and accurate websites." Also serves ACT tutoring: the Enhanced ACT is full of figures, graphs and geometry diagrams that are unreadable as text. | | Flash-Next | Yes, cheap | 0.90 GB, ships a Qwen3-VL ViT. It is CPU-resident so there is no VRAM workspace problem at all. Grab it. | | Uncensored 27B | No | 0.63 GB, but this slot exists for text the judge will not write. Skip and keep the VRAM. | | Router | No | It emits a label. Vision is pure overhead. | | GLM-5.3 full | N/A | No mmproj published. | | MiMo | Ships vision (ViT depth 28) AND audio + an audio tokenizer | Conversion will likely DROP them, and that is a free saving with zero text-quality cost per mimo-v2.6-feasibility. Do not fight to keep them. | VERDICT: take the mmproj for the 27B judge and for Flash-Next. Skip it everywhere else. Total cost ~1.5 GB of download.

## LEVER #3 — OTHER SYSTEM-WIDE ITEMS, ordered by value-per-effort

1. Verify reasoning effort is `xhigh` on the 27B. `--chat-template-kwargs '{"reasoning_effort":"xhigh"}'`. Worth 8 AA index points (34 vs 26) and costs nothing. Check the live llama-server line rather than assuming.
2. Make long jobs durable. The GLM download died in tmux and lost 242 GiB with no forensic trail (glm-5.3-download). Every multi-hour job on this box goes in a systemd user unit with `loginctl enable-linger`, logging with timestamps. This is a system-reliability fix, not a speed one, and it has already cost him days.
3. `-b 4096 -ub 4096` everywhere. Prefill-only, ~2x, free, no quality cost.
4. Disable NUMA balancing when running a giant: `echo 0 > /proc/sys/kernel/numa_balancing`, plus `numactl --interleave=all`.
5. Raise memlock so `--mlock` works: `ulimit -l unlimited` or systemd `LimitMEMLOCK=infinity`. Without it a memory-pressure event can swap a 400 GB model's own pages, which is catastrophic.
6. Measure PREFILL before decode. Nothing on this box has a measured prefill number for any giant, and prefill is what makes a large context unusable, not RAM. At 10 t/s prefill a 100K prompt is 2.8 hours.
7. Backup. jarvis-backup records the restic restore as blocked. The new 4TB drive is the first local bulk storage he has ever had; models that cost days to fetch currently exist in one place.

## STILL NOT RESEARCHED

- Fork/engine merge statuses as a set (ik_llama NUMA mirror #2030, MoE expert cache #24528, oversized-moe-runtime) under the new "anything that runs" constraint.
- No blind-verification pass has been run on this file or on model-tier-ceiling / context-and-speed-per-model / model-pull-and-flags.

## *** Sep 23 2026 — MEASURED ON THE BOX. THREE FINDINGS, ONE OF THEM BIG. [MEASURED] ***

### FINDING A: CONFIRMED — THE DIMMS ARE RATED 2133 AND RUNNING AT 1866. A REAL ~14% LOSS.

`dmidecode -t memory`, every module identical:

```
Size: 32 GB   Type: DDR4   Rank: 2
Speed: 2133 MT/s              <- what the DIMMs are rated for
Configured Memory Speed: 1866 MT/s   <- what they actually run at
```

Locators DIMM_A1, A2, B1, B2 (NODE 1), C1, C2, D1, D2 (NODE 2), E1, E2... (NODE 3) — i.e. two DIMMs per channel, 4 channels per socket, 16 x 32 GB dual-rank RDIMM = 512 GB. CAUSE: 2 DIMMs per channel with dual-rank modules is exactly the configuration that forces Haswell-EP down from 2133 to 1866. This is not a BIOS mistake to fix for free; it is a population consequence. Theoretical per socket: 59.7 GB/s at 1866 vs 68.3 GB/s at 2133. So the current population costs ~14% of every CPU-resident model's decode speed.

### FINDING B: CONFIRMED — CROSS-SOCKET IS EXPENSIVE, AND INTERLEAVING MAKES THINGS WORSE, NOT BETTER

`numactl --hardware`: 2 nodes, node 0 = 257,870 MB, node 1 = 257,986 MB (~503 GiB total), 36 CPUs each. `node distances: 0->0 = 10, 0->1 = 21` — remote memory costs 2.1x local. mbw, socket-local vs interleaved: | Method | --cpunodebind=0 --membind=0 | --interleave=all | Interleaved is... | | MEMCPY | 5,790.7 MiB/s | 4,831.7 MiB/s | 17% SLOWER | | DUMB | 11,531.0 MiB/s | 9,845.0 MiB/s | 15% SLOWER | | MCBLOCK | 5,926.2 MiB/s | 5,592.4 MiB/s | 6% slower | *** THIS IS DIRECT LOCAL EVIDENCE FOR THE "DUAL-SOCKET UNDERPERFORMS SINGLE-SOCKET" FINDING already in cpu-moe-speed-levers, which was previously only community hearsay. It is now measured on Jack's own box. *** CONSEQUENCE: `--interleave=all` is NOT automatically the right flag. For any model that FITS one socket (Flash-Next at 103.7-175.3 GiB, Hy4 IQ1_M at 219.2 GiB, GLM-5.3-Flash at 186 GiB), pin it to one socket with `numactl --cpunodebind=0 --membind=0` instead. Interleaving only makes sense for a model too big to fit one socket (GLM-5.3 full at 435 GiB, MiMo at 498 GiB), which is forced to span them anyway.

### FINDING C: *** mbw CANNOT MEASURE THIS MACHINE'S PEAK BANDWIDTH — IT IS SINGLE-THREADED. DO NOT USE THESE NUMBERS TO VALIDATE OR REPLACE THE 39 GB/s CONSTANT. ***

mbw's best result, DUMB at 11,531 MiB/s, is 12.09 GB/s of copy = ~24.2 GB/s of actual memory traffic (a copy reads and writes, so traffic is 2x the reported rate). But that is ONE THREAD. A single Haswell core cannot saturate four memory channels; peak bandwidth needs many threads. llama.cpp decodes with dozens. So the 39 GB/s figure that every speed estimate in this memory divides by is still UNVALIDATED. The mbw run neither confirms nor refutes it. THE PROPER MULTI-THREADED TEST, still to run:

```bash
sudo apt install -y sysbench
# one socket, 18 threads (its physical cores):
numactl --cpunodebind=0 --membind=0 sysbench memory --memory-block-size=1M \
    --memory-total-size=200G --memory-oper=read --threads=18 run
# both sockets, 36 threads:
numactl --interleave=all sysbench memory --memory-block-size=1M \
    --memory-total-size=200G --memory-oper=read --threads=36 run
```

WHAT GOOD LOOKS LIKE at 1866: socket-local read should approach 45-55 GB/s of the 59.7 theoretical. If it lands near 39, the constant is right and honest. If it lands near 55, every decode estimate in this memory is ~40% pessimistic.

## *** THE REAL HARDWARE LEVER IS NOT THE CLOCK, IT IS CAPACITY: 1 TB OF RAM UNLOCKS NUMA MIRRORING FOR GLM-5.3 FULL ***

cpu-moe-speed-levers concluded flatly that "NO QUANT OF GLM-5.3 FULL IS BOTH MIRRORABLE AND GOOD" — because mirroring needs 2 x 435 = 870 GiB against 503. At 1 TB that door opens, and mirroring is worth a measured 1.47-1.63x on his single best model. Separately, mimo-v2.6-feasibility notes MiMo at ~498 GiB against 503 GiB survives only by mmap paging; 1 TB makes it properly resident with room for KV. TWO PATHS, AND THEY TRADE AGAINST EACH OTHER: | Path | Capacity | Speed | What it unlocks | | 8 x 64 GB at 1 DIMM/channel | 512 GB (same) | 2133, +14% | a flat ~14% on everything, plus 8 free slots | | 16 x 64 GB at 2 DIMM/channel | 1 TB | 1866 (same) | GLM-5.3 mirroring (~1.6x), MiMo fully resident | The 1 TB path is worth far more than the clock path — 1.6x on the capability model beats 14% everywhere. VERIFY BEFORE BUYING: his current modules are `Rank: 2` (dual-rank RDIMM). 64 GB DDR4 modules come as dual-rank RDIMM (2Rx4) or quad-rank LRDIMM. mimo-v2.6-feasibility already warns that quad-rank LRDIMMs in all 16 slots commonly drop to 1600, which would LOSE ~25% and defeat the purpose. Check the Z10PG-D16 QVL for 64 GB 2Rx4 RDIMM at 2DPC before spending anything. Prices not yet researched.

## *** Sep 23 2026 — THE sysbench RESULT IS A CACHE MEASUREMENT, NOT DRAM. 311 GB/s IS 5x FASTER THAN PHYSICS ALLOWS. ***

Ran: `numactl --cpunodebind=0 --membind=0 sysbench memory --memory-block-size=1M --memory-total-size=200G --memory-oper=read --threads=18 run` Result: 311,870.63 MiB/sec (~327 GB/s), 204,786 MiB in 0.6531 s, avg latency 0.06 ms. THIS IS WRONG, AND THE WAY TO KNOW IS THAT IT BEATS THE THEORETICAL MAXIMUM. One socket at DDR4-1866 across 4 channels tops out at 59.7 GB/s. A measured 327 GB/s is 5.5x the hardware ceiling, so it cannot be DRAM traffic. CAUSE: `--memory-block-size=1M` gives each thread a 1 MB buffer. 18 threads x 1 MB = 18 MB, which fits entirely inside the E5-2699 v3's 45 MB L3 cache. sysbench then hammers that buffer in cache and never touches DRAM. This measured L3 bandwidth, which is a real and plausible ~327 GB/s for an 18-core Haswell, and completely irrelevant to model decode. THE GENERAL RULE, worth keeping: any memory-bandwidth number above ~60 GB/s per socket on this box is measuring cache. Sanity-check every result against the theoretical ceiling BEFORE believing it. THE FIX — use STREAM, the standard tool, sized well beyond cache:

```bash
sudo apt install -y build-essential
wget https://www.cs.virginia.edu/stream/FTP/Code/stream.c
gcc -O3 -fopenmp -DSTREAM_ARRAY_SIZE=800000000 -mcmodel=medium stream.c -o stream
OMP_NUM_THREADS=18 numactl --cpunodebind=0 --membind=0 ./stream    # one socket
OMP_NUM_THREADS=36 numactl --interleave=all ./stream               # both
```

STREAM_ARRAY_SIZE 800,000,000 doubles = 6.4 GB per array, three arrays = 19.2 GB working set, far beyond any cache. Read the Triad figure; that is the one comparable to model decode. OR, the sysbench fix if he prefers it: raise `--memory-block-size` to 64M or larger so each thread's buffer exceeds L3. WHAT TO EXPECT: socket-local Triad in the 40-50 GB/s range at 1866. If it lands near 39 the constant used throughout this memory is honest. If it lands near 55, every CPU decode estimate on file is ~40% pessimistic and should be revised upward.

## *** Sep 23 2026 — STREAM RESULT. THE 39 GB/s CONSTANT IS VALIDATED, BUT ONLY FOR DUAL-SOCKET. FINDING B IS OVERTURNED FOR MULTI-THREADED WORK. [MEASURED] ***

Array 800,000,000 elements, 6.0 GiB per array, 17.9 GiB total — correctly beyond the 45 MB L3. Solution validated on both runs. | Run | Copy | Scale | Add | Triad | | `OMP_NUM_THREADS=18 --cpunodebind=0 --membind=0` | 29,808 | 19,519 | 21,576 | 21,570 MB/s = 21.57 GB/s | | `OMP_NUM_THREADS=36 --interleave=all` | 64,225 | 46,934 | 51,050 | 51,035 MB/s = 51.04 GB/s | Ignore the Copy line on both runs. Copy is ~1.5x Scale, which is impossible for two loops doing the same traffic; gcc substitutes `memcpy` with non-temporal stores and skips the read-for-ownership. Triad is the honest figure and the one comparable to model decode.

RECONCILING THIS WITH FINDING B (mbw said interleaving was 15-17% SLOWER): both results are real; they measure different regimes. mbw is SINGLE-THREADED and therefore latency-bound — one core cannot saturate a memory controller, so the only thing interleaving changes for it is that half its accesses now pay the 2.1x remote penalty. STREAM at 36 threads is BANDWIDTH-bound — it saturates both controllers, so aggregating two sockets' channels wins outright. llama.cpp decodes with dozens of threads and is bandwidth-bound, so the STREAM regime is the one that governs, not the mbw regime. *** CONSEQUENCE, AND IT REVERSES EARLIER ADVICE: DO NOT PIN A MODEL TO ONE SOCKET JUST BECAUSE IT FITS. *** Interleaved is 2.37x socket-local on Triad. Flash-Next (103.7-175.3 GiB), Hy4 IQ1_M (219.2 GiB) and GLM-5.3-Flash (186 GiB) all fit inside one socket's 251 GiB, and Finding B said to pin them. That was wrong for a multi-threaded decode. Run them `--numa distribute` / `--interleave=all` across both sockets. Pinning costs roughly 2.4x of bandwidth to save a QPI tax that only matters to a single thread.

IS THE 39 GB/s CONSTANT HONEST? llama.cpp typically achieves 65-80% of STREAM Triad. 0.65-0.80 x 51.04 = 33-41 GB/s. So 39 GB/s sits at the top of the realistic band and every dual-socket decode estimate on file is right, or mildly optimistic — NOT 40% pessimistic. No upward revision. For anything pinned single-socket the governing figure is 0.65-0.80 x 21.57 = 14-17 GB/s, i.e. those estimates would be ~2.4x too fast — which is the arithmetic reason the pinning advice had to go.

## *** OPEN AND POSSIBLY WORTH ~40% ON EVERYTHING: BOTH TRIAD FIGURES ARE LOW AGAINST THEORETICAL. ***

Socket-local 21.57 vs 59.7 theoretical = 36%. Dual 51.04 vs 119.5 = 43%. A healthy STREAM Triad is 60-75% of theoretical. Both runs are well under that, so this is not a NUMA artifact — the whole machine is under-delivering, and the deficit is roughly the size of every model-choice decision combined. LEADING SUSPECT, AND IT IS FREE TO TEST: uncore frequency scaling / a power-saving BIOS profile. Haswell-EP with a conservative power profile drops the uncore (ring + memory controller) clock under load and can lose 30-40% of memory bandwidth while the core clocks look fine. A `powersave` cpufreq governor does the same. CHECK AND FIX, in this order:

```bash
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor     # want: performance
grep MHz /proc/cpuinfo | sort -u | head
sudo apt install -y linux-tools-common linux-tools-generic msr-tools
sudo cpupower frequency-set -g performance
sudo modprobe msr && sudo rdmsr 0x620                          # UNCORE_RATIO_LIMIT
# then RE-RUN BOTH STREAM LINES and compare Triad
```

Then BIOS: set the power/performance profile to Performance (not Energy Efficient), disable uncore frequency scaling / set uncore to max, confirm Turbo on, and confirm memory is not in a power-down or 1N command-rate mode. If Triad moves from 51 to ~75 GB/s dual-socket, every CPU decode estimate in this memory goes up ~45% and it costs nothing. SECOND SUSPECT if the governor is already `performance` and BIOS is already Performance: re-run socket-local with `OMP_NUM_THREADS=36 --cpunodebind=0 --membind=0` (all 36 logical CPUs of node 0). If socket-local Triad jumps well above 21.57, the 18-thread run was simply under-saturating one socket and the 2.37x interleave advantage is overstated — but the direction of the advice does not change.

## *** Sep 23 2026 — LEVER #1 IS SOLVED AND IT WORKED. UNCORE FLOOR WAS THE BOTTLENECK. +37% SINGLE-SOCKET, +16.5% DUAL, FREE. [MEASURED] ***

THE CAUSE, confirmed by `rdmsr 0x620` returning `c1e`: MSR_UNCORE_RATIO_LIMIT bits 6:0 = max ratio, bits 14:8 = min ratio. `0xc1e` decodes to max 30 (3.0 GHz, correct) and min 12 (1.2 GHz). Uncore frequency scaling was free to drop the ring bus and memory controllers to 40% of full speed, and under a memory-bound load it does exactly that, because the cores look idle while stalled on memory. THE FIX (both applied together):

```bash
sudo cpupower frequency-set -g performance      # applied across all 72 CPUs
sudo wrmsr -a 0x620 0x1e1e                      # pin uncore MIN = MAX = 30 (3.0 GHz)
sudo rdmsr -a 0x620 | sort -u                   # verify: single line "1e1e"
```

NEITHER SURVIVES A REBOOT. Put both in a systemd unit with `After=multi-user.target` before trusting any benchmark taken later. MEASURED BEFORE vs AFTER (STREAM Triad, 17.9 GiB working set): | Run | Before | After | Gain | | 18 threads, `--cpunodebind=0 --membind=0` | 21.57 GB/s | 29.52 GB/s | +36.9% | | 36 threads, `--cpunodebind=0 --membind=0` | not run | 28.54 GB/s | — | | 36 threads, `--interleave=all` | 51.04 GB/s | 59.48 GB/s | +16.5% |

SECOND SUSPECT RULED OUT: 36 threads socket-local (28.54) is SLIGHTLY SLOWER than 18 threads socket-local (29.52). Hyperthreading adds contention and no bandwidth, which proves 18 threads already fully saturates one socket's 4 channels. The original 18-thread run was not under-sampling. Practical flag rule: use physical cores only, `-t 18` per socket / `-t 36` total — never 72.

DUAL-SOCKET SCALING IS NOW EXACTLY 2.01x (59.48 / 29.52). Clean linear scaling from doubling the channel count, which is what should happen. The earlier 2.37x was an artifact of the pinned run being uncore-throttled harder than the interleaved one. The advice is unchanged and now rests on a clean number: INTERLEAVE, DO NOT PIN. Worth 2x.

EFFICIENCY IS NOW HEALTHY, and there is a strong internal consistency check. Socket-local 29.52/59.7 = 49.4%; dual 59.48/119.5 = 49.8%. Identical, as they should be. Converting STREAM's counted traffic to actual DRAM traffic: Triad's write stream also pays a read-for-ownership, so real traffic is 4/3 x 59.48 = 79.3 GB/s; Copy at 78.53 GB/s counted uses non-temporal stores (no RFO) so its real traffic is 78.5 GB/s. Two different kernels agree on ~79 GB/s = 66% of the 119.5 theoretical, which is a normal, healthy figure for 2DPC DDR4-1866 Haswell-EP. The machine is no longer misconfigured.

## *** WHAT THIS DOES TO THE 39 GB/s CONSTANT: IT IS NOW A FLOOR, NOT A BEST ESTIMATE. THE BAND IS 39-55 GB/s AND ONLY A REAL RUN CAN CLOSE IT. ***

Two defensible bases, and they disagree:

- Conservative (Triad-reported basis): llama.cpp empirically gets 65-80% of reported STREAM Triad -> 0.65-0.80 x 59.48 = 38.7-47.6 GB/s. The 39 constant sits at the bottom. Dual-socket decode estimates on file are 0-22% pessimistic, midpoint ~+10%.
- Optimistic (read-traffic basis): model decode is a near-pure sequential READ of weights with almost no writes, so it never pays the read-for-ownership tax that Triad does. Against the ~79 GB/s real-traffic ceiling the achievable figure is materially higher, plausibly 50-55 GB/s, i.e. estimates ~1.3-1.4x pessimistic. *** DO NOT REVISE THE PER-MODEL TABLES ON THEORY. THE DEFINITIVE MEASUREMENT IS ONE RUN: ***

```bash
# any CPU-resident GGUF, GPU disabled, physical cores, interleaved:
numactl --interleave=all llama-bench -m <model.gguf> -ngl 0 -t 36 -p 0 -n 128
```

Then back-solve: effective GB/s = decode_t/s x active_params x bpw / 8. That single number replaces every estimate in context-and-speed-per-model and cpu-moe-speed-levers and ends the guessing. Do this BEFORE spending money on the 1 TB RAM path, because it also tells you what fraction of theoretical llama.cpp actually converts, which is what determines whether more capacity or more bandwidth is the better buy.

## *** Sep 23 2026 — SECOND SWEEP OF FREE LEVERS. ONE REAL FIND, ONE FALSE ALARM I RAISED MYSELF, TWO WORTH TESTING. [MEASURED] ***

FALSE ALARM, AND IT WAS MINE: `GGML_AVX2:BOOL=OFF` / `GGML_FMA:BOOL=OFF` IS THE CORRECT AND EXPECTED STATE. The build also shows `GGML_NATIVE:BOOL=ON` and `CMAKE_BUILD_TYPE=Release` (`-O3 -DNDEBUG`). In llama.cpp's CMake the explicit instruction-set options are deliberately forced OFF when `GGML_NATIVE` is ON, because `-march=native` already enables every feature the host CPU has, AVX2 and FMA included. Reading those two OFF lines as "built without AVX2" is a misread of the cache file. Do not rebuild on that basis. Hard confirmation (run it before trusting either way): `objdump -d ~/llama.cpp/build/bin/*.so | grep -c -E "vfmadd"` should be non-zero, and `grep -o '\-march=[a-z0-9]*' ~/llama.cpp/build/ggml/src/ggml-cpu/CMakeFiles/*/flags.make | sort -u` should print `-march=native`.

REAL FIND: `kernel.numa_balancing = 1`. IT IS ON. Automatic NUMA balancing constantly migrates pages toward whichever thread touched them last. With a 400+ GiB model deliberately interleaved across both sockets and 36 threads touching everything, there is no correct placement to converge on, so it thrashes and burns bandwidth on migration. Fix, free and immediate: `sudo sysctl -w kernel.numa_balancing=0`, persist in `/etc/sysctl.d/`. This was already item 4 on the untested list; it is now confirmed as actually enabled.

GPUs ARE CLEAN, NOTHING BROKEN. Both Tesla V100-PCIE-16GB at Gen3 x16 current, Gen3 x16 max, persistence mode Enabled. No riser or bifurcation problem. `nvidia-smi topo -m`: PHB, both cards on NUMA node 0, CPU affinity 0-17,36-53. *** CONSEQUENCE WORTH REMEMBERING: for any GPU-resident or hybrid slot, CPU threads should be pinned to node 0, because host-to-device traffic from node 1 crosses QPI. This conflicts with the interleave-everything rule and the right answer depends on the slot: pure CPU model = interleave, GPU or hybrid model = node 0. *** ECC IS ENABLED ON BOTH CARDS. Turning it off frees roughly 1 GiB of usable VRAM per card (~2 GiB total) and gains a few percent of memory bandwidth. `sudo nvidia-smi -e 0`, then reboot, then verify with `nvidia-smi --query-gpu=ecc.mode.current,memory.total --format=csv`. Relevant because orchestrator-slot-plan records a 4.27 GiB CLIP workspace as the thing that made a single-card 27B layout look impossible; 2 GiB back is half of that. Tradeoff: no single-bit correction on used Teslas. For inference a flipped bit is a wrong token, not a crash, so this is usually worth taking.

TRANSPARENT HUGE PAGES: `always [madvise] never`, and `AnonHugePages: 0 kB` confirms zero are in use. Hugepagesize is 2048 kB, no 1 GB pages configured. The TLB problem is real: 435 GiB on 4 KB pages needs over 100 million page-table entries and the TLB thrashes continuously. But THP cannot back llama.cpp's default mmap'd, file-backed weights. The route that would work is `--no-mmap` (making the weights anonymous memory) plus THP set to `always`. UNTESTED, and it has a real downside: a 400 GB anonymous allocation under THP `always` can stall on khugepaged and make load times much worse. Measure with llama-bench before adopting; do not enable blind.

`vm.zone_reclaim_mode = 0` is already correct. Leave it.

C-STATES AND MITIGATIONS: LOW EXPECTED VALUE HERE, AND I AM NOT RECOMMENDING THEM YET. Available idle states are POLL, C1, C1E, C3, C6. Mitigations are all active (PTI, retpolines, IBPB conditional, IBRS_FW, MDS/mmio clear-CPU-buffers, vmscape IBPB), cmdline is bare. The large published mitigation costs apply to syscall- and I/O-heavy workloads. llama.cpp's decode loop is compute and memory bound and makes very few syscalls, so expect low single digits, not tens of percent. Both changes need a kernel cmdline edit and a reboot. Additional reason for caution on `mitigations=off`: jarvis-run-host-commands records a full unrestricted shell tool server running on this box, which raises the cost of weakening CPU isolation. Revisit only after the llama-bench baseline exists.

## Sep 23 2026 — CLOSING NUMBERS FOR THE BANDWIDTH WORK [MEASURED]

- AVX2/FMA CONFIRMED PRESENT. `objdump -d ~/llama.cpp/build/bin/*.so | grep -c vfmadd` = 1105. The build is correct; the `GGML_AVX2=OFF` false alarm is fully closed. (The `flags.make` path I gave does not exist in this build layout; ignore that error.)
- `kernel.numa_balancing=0` APPLIED and persisted to `/etc/sysctl.d/99-jarvis.conf`. Dual-socket Triad 59,479 -> 60,474 MB/s, +1.67%. *** TREAT +1.67% AS A FLOOR, NOT THE EXPECTED VALUE: STREAM is a poor probe here because its threads touch their own slices consistently, so auto-NUMA has almost nothing to thrash on. The case it actually hurts is 36 threads sweeping all experts of a 400 GiB interleaved model, which STREAM cannot simulate. Re-judge with llama-bench. ***
- RUNNING TOTAL ON FREE FIXES: 51.04 -> 60.47 GB/s dual-socket Triad, +18.5%, from cpufreq governor + uncore floor pin + numa_balancing off.
- *** DONE Sep 23 2026 04:41 UTC — `jarvis-perf.service` CREATED AND ENABLED. The governor and uncore pin now persist. *** Written to `/etc/systemd/system/jarvis-perf.service`, `Type=oneshot` + `RemainAfterExit=yes`, `After=multi-user.target`, `ExecStartPre=/sbin/modprobe msr`, then two `ExecStart=/bin/sh -c` lines: `cpupower frequency-set -g performance` and `wrmsr -a 0x620 0x1e1e`. Binaries are at `/usr/bin/cpupower` and `/usr/sbin/wrmsr`; both resolve fine under systemd's default PATH, so no absolute paths were needed. `numa_balancing=0` was ALREADY persisted separately in `/etc/sysctl.d/99-jarvis.conf`, so the unit deliberately does not touch it. VERIFIED at enable time: `active (exited)`, all three processes `status=0/SUCCESS`, `scaling_governor` = `performance`, `rdmsr -a 0x620 | sort -u` = single line `1e1e` across all 72 CPUs. STILL PROVISIONAL UNTIL A REBOOT ACTUALLY TESTS IT — enable-time success only proves the unit runs, not that it runs early enough on boot. Post-reboot check: `systemctl is-active jarvis-perf.service`, then re-read the governor and `rdmsr -a 0x620`.

## *** Sep 23 2026 — THE PERSISTENCE UNIT EXISTS AND SURVIVED A REBOOT. THE "NOT YET DONE" ITEM IS CLOSED. [MEASURED] ***

`/etc/systemd/system/jarvis-perf.service`, enabled, `Type=oneshot` + `RemainAfterExit=yes`, `After=multi-user.target`:

```
ExecStartPre=/sbin/modprobe msr
ExecStart=/bin/sh -c 'cpupower frequency-set -g performance'
ExecStart=/bin/sh -c 'wrmsr -a 0x620 0x1e1e'
```

Binaries are `/usr/bin/cpupower` and `/usr/sbin/wrmsr`; both resolve under systemd's default PATH, so absolute paths are not needed. `kernel.numa_balancing=0` was already persisted separately in `/etc/sysctl.d/99-jarvis.conf` and is NOT in this unit. VERIFIED ACROSS TWO REBOOTS: `systemctl is-active` = active, `scaling_governor` = `performance`, `rdmsr -a 0x620 | sort -u` = single line `1e1e`, `/proc/sys/kernel/numa_balancing` = 0. Benchmarks taken after a reboot now measure the FAST configuration.

## *** Sep 23 2026 — FIRST REAL llama-bench CALIBRATION. THE 39 GB/s CONSTANT IS MILDLY OPTIMISTIC, NOT PESSIMISTIC. PROVISIONAL. [MEASURED] ***

Ran the calibration this file called for, on the live 27B GGUF with `-ngl 0`. THE MODEL IS DENSE, WHICH REMOVES THE DIVISOR AMBIGUITY. llama-bench header: `qwen35 27B Q4_K - Medium | 17.66 GiB | 26.90 B params`. No MoE. The hybrid-SSM layout changes which layers hold KV, not which weights are read, so active params = total params and bytes/token = the full 17.66 GiB. RESULT: tg128 = 1.93 t/s (`-t 36`, `--interleave=all`). Back-solved: 1.93 x 17.66 GiB = 34.08 GiB/s = 36.6 GB/s effective. | Basis | Figure | 36.6 is | | STREAM Triad dual, post-fix | 60.47 GB/s | 60.5% of it | | the 39 GB/s constant | 39 | 6% BELOW | | conservative band predicted here | 38.7-47.6 | under the floor | | optimistic band predicted here | 50-55 | nowhere near | *** SO THE 39 CONSTANT IS NOT A FLOOR. IT IS MILDLY OPTIMISTIC, AND EVERY DUAL-SOCKET DECODE ESTIMATE ON FILE IS ~6% TOO FAST. *** The "estimates are 1.3-1.4x pessimistic" branch is dead. The 1 TB RAM path must now be justified on CAPACITY alone (mirroring, MiMo residency) — llama.cpp is not converting bandwidth better than assumed. *** PROVISIONAL. DO NOT REVISE THE PER-MODEL TABLES YET — THE MEASUREMENT HAS A KNOWN METHOD FLAW. *** The page cache was warmed with a SINGLE-THREADED `cat`, so first-touch put all 17.66 GiB of page-cache pages on one node, and `numactl --interleave=all` does not relocate existing page-cache pages. The interleave flag therefore did nothing. Tell-tale: the unpinned run (1.92) and the "interleaved" run (1.93) agreed to 0.01 t/s, because placement was identical both times. THE CLEAN RE-RUN, still owed — and note the flag names on b11089:

```bash
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
numactl --interleave=all llama-bench -m "$MODEL" -ngl 0 -t 36 -p 0 -n 128 -r 3 -lm none --numa numactl
numactl --cpunodebind=0 --membind=0 llama-bench -m "$MODEL" -ngl 0 -t 18 -p 0 -n 128 -r 3 -lm none --numa numactl
```

*** `--mmap` / `--no-mmap` DO NOT EXIST on llama-bench b11089. *** The equivalent is `-lm, --load-mode <auto|none|mmap|mlock|mmap+mlock|dio>`; `none` puts weights in anonymous memory under the numactl policy. And `--numa` defaults to DISABLED, so llama.cpp was not honoring the numactl policy for thread placement either — pass `--numa numactl`. Signature that `-lm none` took effect: a long pause before the table while 18 GiB is read from NVMe, and `free` showing `used` climb rather than `buff/cache`. FRAMING TO CARRY FORWARD: this is a DENSE SEQUENTIAL READ, the friendliest possible access pattern. The CPU giants are MoE and gather scattered experts per token, so whatever this settles on is a CEILING for GLM-5.3, Flash-Next and MiMo, not a like-for-like.

## *** ECC OFF IS A DEAD END ON V100. IT FREES ZERO VRAM. [MEASURED — supersedes the ECC claim in LEVER #3's second sweep] ***

Applied `nvidia-smi -e 0`, rebooted, ECC confirmed Disabled on both cards. `llama-server --list-devices` usable VRAM stayed at 16,144 MiB per card, unchanged; `nvidia-smi memory.total` stayed 16,384. V100 HBM2 uses dedicated ECC storage rather than carving capacity out of the user-visible pool. The "roughly 1 GiB of usable VRAM per card (~2 GiB total)" line above is WRONG — remove it from planning. It does not half-solve the 4.27 GiB CLIP workspace and it does not unblock `-b 4096`. Consequences and the recommendation to turn ECC back on are in llama-server-live-unit.

## GPU POWER LIMIT: SETTLED AT 200 W, AND TWO UNITS WERE FIGHTING OVER IT. [MEASURED]

`gpu-tune.service` set `-pl 250` while `nvidia-powercap.service` set `-pl 200`, with no ordering between them, so the effective cap was nondeterministic. `nvidia-powercap.service` also carried a systemd dependency cycle that silently prevented llama-server from starting at boot (full detail in llama-server-live-unit); it is now disabled, leaving `gpu-tune.service` the single owner. Six alternating bench runs, first discarded: 250 W and 200 W differ by under 0.2% and interleave. 50 extra watts per card buys nothing. `gpu-tune.service` set to `-pl 200`. Consistent with the existing power-curve data; do not revisit.

## *** Sep 23 2026 — BLIND VERIFICATION PASS. 81.4% ACCURATE (35/43), BELOW THE 95% BAR. THE RAM-PURCHASE SECTION IS WHERE IT FAILS. ***

Independent auditor checked every external claim against Intel ARK, Supermicro's memory config guide, NVIDIA's Volta whitepaper, the STREAM reference, llama.cpp CMake source and the Debian llama-bench manpage. Every one of ~25 arithmetic derivations reproduced exactly — including the 4/3 RFO correction and the Copy-vs-Scale non-temporal-store diagnosis (predicted 1.50 against measured 1.527, and 1.333 against 1.32). The errors are concentrated in the DIMM section and in one GPU claim.

### *** CORRECTION 1, AND IT INVERTS A FOUR-FIGURE PURCHASE: THE LRDIMM WARNING IN THIS FILE IS BACKWARDS. ***

This file states twice that quad-rank 64 GB LRDIMMs in all 16 slots "commonly drop to 1600, which would LOSE ~25%", and builds the whole "two paths trade against each other" table on it. [SOURCE] Supermicro X10 (E5-2600 v3) Memory Config Guide:

- dual-rank RDIMM, 1-4 DIMMs/CPU → 1600/1866/2133; 5-8 DIMMs/CPU → 1600/1866 only.
- quad-rank LRDIMM, 5-8 DIMMs/CPU → 1600/1866/2133. *** LRDIMM HOLDS 2133 AT 2DPC, EXACTLY WHERE DUAL-RANK RDIMM DOES NOT. *** So the 16 x 64 GB LRDIMM path plausibly delivers 1 TB AND 2133 — capacity AND the +14% — and the "1.6x mirroring beats 14% clock, pick one" framing dissolves. The Finding A diagnosis (why Jack's CURRENT dual-rank RDIMMs at 2DPC run 1866) is still correct; the counter-warning about LRDIMMs is not. CORRECTION 2, same section: the part this file tells him to verify probably does not exist for his platform. 64 GB DDR4 2Rx4 RDIMM is a 16 Gb-die part that shipped at DDR4-3200 and is marked "Not Compatible with Skylake CPU" — two generations after Haswell-EP. At 2133 on this board, 64 GB means 4Rx4 LRDIMM (PC4-17000L). *** REVISED ACTION: price 64 GB 4Rx4 LRDIMM and check the Z10PG-D16 QVL for THAT, not for 2Rx4 RDIMM. ***

### CORRECTION 3 — THE ECC CLAIM WAS FALSIFIABLE FROM NVIDIA'S OWN WHITEPAPER BEFORE THE REBOOT WAS SPENT

[SOURCE] NVIDIA Volta Architecture Whitepaper: "With V100 and P100, ECC can be active without a bandwidth or capacity penalty." V100 HBM2 uses native/sideband ECC in a separate region; the 6.25% carve-out belongs to GDDR5 (K40). Today's measurement (usable VRAM unchanged at 16,144 MiB) confirms it empirically. The retraction already in this file fixes the CAPACITY half. The "plus a few percent bandwidth" half is ALSO wrong and is hereby struck too. ECC off on V100 buys nothing at all.

### THE 65-80%-OF-TRIAD RULE IS FOLKLORE, NOT A SOURCED CONSTANT — AND OUR OWN RUN FELL OUTSIDE IT

No primary source exists for "llama.cpp typically achieves 65-80% of STREAM Triad". It is load-bearing here: both the 38.7-47.6 and 33-41 GB/s bands rest on it, as does the "39 is honest" conclusion. Our own llama-bench landed at 36.6/60.47 = 60.5%, BELOW the asserted band. Rewrite the band from the measurement, not the rule of thumb, and label the 65-80% figure an assumption wherever it is used.

### SMALLER CORRECTIONS

- Headline unit slip: "311 GB/s is 5x faster than physics allows." The figure is 311,870 MiB/s = 327 GB/s = 5.5x. The body is right; the heading mislabels MiB/s as GB/s. Should read "327 GB/s / 5.5x".
- THP claim is right but dated. "THP cannot back file-backed mmap" matches kernel docs, but modern ext4/XFS get large folios in the page cache, so file-backed mappings may already get some large-page benefit and `AnonHugePages: 0` does not prove otherwise. The `--no-mmap` + THP experiment may show a smaller delta than expected.
- ik_llama NUMA mirror #2030 is a DISCUSSION, not a PR. The implementation PR is #2396; the code lives at `mikechambers84/ik_llama.cpp:numa-mirror`. Checked live Sep 23: still unmerged, last substantive activity June 2026, ikawrakow wants cleanup + rebase + `llama-sweep-bench` numbers. Gains revised DOWN to 18-58% (18% at NPS=1) from the 47-63% recorded elsewhere.
- `GGML_NATIVE=ON` defaults AVX2/FMA OFF rather than forcing them; an explicit `-DGGML_AVX2=ON` still takes effect.
- Max uncore ratio 30 being "correct for this SKU" is UNVERIFIABLE — Intel publishes no per-SKU uncore max.
- CONFIRMED exact: all DDR4 bandwidth tables; ARK's 68 GB/s/socket; the 2DPC dual-rank drop; MSR 0x620 bit layout and the 0xc1e decode; STREAM's 24-byte Triad counting and the 4/3 RFO correction; the sysbench-measured-L3 self-catch; llama-bench's `-lm` and `--numa` flags verbatim against the manpage; the 49.4%/49.8% internal consistency check; and all four HuggingFace mmproj/imatrix file sizes.

## *** Sep 23 2026 — HARDWARE UPGRADE SWEEP. THE BIGGEST FIND IS A ~$200 CPU SWAP, NOT THE $3,000 RAM PATH. Blind check 94%, the one miss was a price range. ***

Jack asked for a massive pass on anything that could improve the system.

### *** FIND #1: 2x Xeon E5-2699 v4 FOR ~$150-240 THE PAIR. THIS IS THE BEST VALUE-PER-DOLLAR ITEM EVER FOUND FOR THIS BOX. ***

ASUS's own ESC4000 G3 tech spec, verbatim: "Intel Xeon processor E5-2600 v4 product family (145W), Intel Xeon processor E5-2600 v3 product family (145W)." The v4 path is officially supported, not a hack. ASUS publishes a CPU Support List naming E5-2699 v4 explicitly (asus.com/us/supportonly/esc4000 g3/helpdesk_cpu/), along with 2697A/2698/2699A/2699R v4. *** MINIMUM BIOS 3104 for E5-2699 v4 (3204 for the A and R variants). FLASH IT WHILE THE v3 CHIPS ARE STILL IN. *** E5-2699 v4 (Intel ARK, read directly): 22 cores / 44 threads, 55 MB L3, 145 W, DDR4 1600/1866/2133/2400, 4 channels, 76.8 GB/s. Against the current E5-2699 v3's 18 cores and 45 MB. PRICES, eBay listings Sep 23 2026 (asking, not sold comps): singles ~$85-110 (one read at $97.72); matched PAIRS $149 + $59.80 shipping from Korea, up to $239.99 US-origin. Call it $200-240 landed. WHAT IT BUYS: +22% cores (36 -> 44 physical), +22% L3, and probably 1866 -> 2133 memory, which is ~+14% on EVERY CPU-resident model. Cores matter here because prefill is compute-bound and prefill is the binding constraint on every giant. *** THE RISK, AND IT IS REAL: multiple unresolved forum reports of the SIBLING board (Z10PE-D16 WS) failing to boot with two v4 CPUs — each works alone in socket 1, BIOS updates did not fix it, one board needed ASUS to reflash a chip. No ASUS erratum exists. Different board from the Z10PG-D16, but buy from somewhere that takes returns. ***

### *** FIND #2, AND IT IS FREE: HIS CURRENT 1866 MAY BE AN ASUS BOARD DERATE, NOT A SILICON LIMIT. CHECK THE BIOS BEFORE SPENDING ANYTHING. ***

This file concluded that 2DPC dual-rank RDIMM forces Haswell-EP to 1866, sourced from Supermicro's X10 guide (confirmed exact: DR RDIMM 2133/1866/1600 at 1/2/3 DPC; QR LRDIMM 2133/2133/1600 — the LRDIMM-holds-2133-at-2DPC asymmetry is real). *** BUT THAT IS A SUPERMICRO SPEC, NOT A HASWELL LAW. Dell's PowerEdge R730 Technical Guide Table 10 lists "RDIMM 1R and 2R ... 2133 MT/s" at BOTH 1 DPC and 2 DPC, dropping to 1866 only at 3 DPC. Lenovo's x3650 M5 guide says the same for v3. Two tier-1 vendors run 2133 at 2DPC where ASUS runs 1866. *** SO: look for a memory-frequency / "DDR Speed" override in the ESC4000 G3 BIOS before buying anything. If it will hold 2133 on the existing DIMMs, that is the same ~14% for $0. Ranked above the CPU swap purely on cost.

### FIND #3: THE 1 TB RAM PATH IS PRICED, AND IT IS ~$3,000

64 GB DDR4-2400 4Rx4 LRDIMM (PC4-19200L), used/open-box eBay Sep 2026: $185-240 each. Micron 4DRx4 pre-owned $185.00, SK Hynix $199.99, open-box Samsung/HP/Hynix $229-240. | option | cost | capacity | speed | unlocks | | 16 x 64 GB LRDIMM | ~$2,960-3,845 | 1 TB | 2133 (v3) / 2400 (v4) | GLM-5.3 NUMA mirroring ~1.6x, MiMo fully resident | | 8 x 64 GB LRDIMM at 1DPC | ~$1,480-1,920 | 512 GB (no gain) | 2133/2400 | clock only, ~+14% | *** THE OLD "CAPACITY vs CLOCK, PICK ONE" FRAMING IS DEAD: LRDIMM gives both. But against Jack's finances (gig income, ~$25/mo paid-services ceiling) a $3,000 spend is out of proportion to a 1.6x on one model. DO THE FREE BIOS CHECK AND THE $200 CPU SWAP FIRST, RE-MEASURE, AND ONLY THEN DECIDE IF RAM IS WORTH IT. ***

### *** FIND #4, THE BIGGEST SOFTWARE LEVER AND IT COSTS NOTHING: CONTINUOUS BATCHING. IT MULTIPLIES THE HARNESS. ***

llama.cpp discussion #18030, measured: Phi-4-mini Q4_K_M, 128-token prompts, RTX 3090 at 128 parallel tasks = 3,973 tok/s aggregate, which the author states is "approximately 15 times better throughput in comparison with plain single task mode." RTX 3060 1,050 tok/s at 128; returns diminish past the peak (256 tasks fell to 3,419). MECHANISM: decode is memory-bandwidth-bound per token, so batching amortizes the weight read across B sequences. That reasoning is standard transformer inference, NOT a llama.cpp-documented claim — maintainer discussion #4130 covers KV sharing and masking and flags a countervailing cost, that attention is computed over the whole KV cache per sequence. *** WHY THIS MATTERS MORE THAN ANY HARDWARE ITEM: agent-harnesses costs a harness at 20-40 SEQUENTIAL model calls per problem. Many of those calls are independent (parallel workers under one manager). Running them across llama-server slots instead of one at a time could cut harness wall-clock several-fold for free. *** Expect well under 15x on 2x V100-16GB with a split model, and KV cache will cap the usable slot count long before 128. Measure it: run the same harness task at --parallel 1 vs 4 and compare wall clock.

### WHAT THIS SWEEP DELIBERATELY DID NOT RE-RESEARCH

GPU upgrades (gpu-upgrade-options), engine alternatives (v100-speed-frontier), per-model quant choice (quant-quality-tables) and the infrastructure gaps (jarvis-system-gaps) are all already covered and were not duplicated. Still genuinely unexamined anywhere: GPU and CPU THERMALS under sustained load. Passively-cooled V100s in a 2U chassis that is thermal-throttling would be free performance; `nvidia-smi --query-gpu=temperature.gpu,clocks.sm,clocks_throttle_reasons.active` during a long run settles it in one command.
