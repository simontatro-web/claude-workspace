# power-thermals-and-tuning

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 23, 2026).
> Cowork-only links kept as page names.
>
> Summary: Sep 23 2026 second-pass system research for jarvis-1 — real wall-power draw and what electricity actually costs per month, V100 thermal thresholds and how to check throttling, UPS sizing, and llama.cpp's unused CPU-affinity flags. Read for "what else can I improve" questions after [[system-performance-levers]], which hit its size cap.

Continues system-performance-levers (bandwidth, uncore, the CPU/RAM upgrade sweep), which is near its size cap. Related: jarvis-system-gaps GAP 4 (power-awareness) and ADD 4 (electricity cost), nvme-drive-failure, llama-server-live-unit. Blind verification pass: 85% first time. The two failures were the electricity rate (too low) and the UPS price/sizing. Both corrected below from the auditor's primary sources.

## *** Sep 23 2026 — JACK: "Power is of no concern to me regarding the cost of it." THE COST ANALYSIS BELOW IS DEAD AS A DECISION INPUT. ***

Do not raise electricity cost as a reason to schedule, cap, or avoid anything. Do not re-derive the monthly bill. Run 24/7 and run overnight batch work freely; the numbers below are kept only as reference if he ever asks what it costs. *** BUT KEEP COST AND CAPACITY SEPARATE — THEY ARE DIFFERENT PROBLEMS AND ONLY ONE IS DISMISSED. *** The 15 A basement circuit is a hard physical limit, and a breaker trip mid-write on a single-drive box is the uncontrolled shutdown behind the whole nvme-drive-failure saga. The GPU power cap, the mutual-exclusion scheduler rule and the UPS all remain justified on UPTIME AND DATA-INTEGRITY grounds, not on the power bill. If anything, his indifference to cost makes the 240 V circuit a purely engineering decision rather than a budget one.

## ELECTRICITY COST REFERENCE ONLY — SUPERSEDED AS A DECISION INPUT, SEE ABOVE

Jack's ceiling on PAID SERVICES is ~$25/month (local-ai-setup). The box's power bill is very likely larger than that, and nobody has measured it. WALL POWER, built up from measured anchors:

- SPECpower_ssj2008 on a Dell R730 with the SAME 2x E5-2699 v3, 64 GB, no GPU: active idle 46.9 W, 100% load 272 W. That is a power-tuned config with 8 DIMMs and an integer workload, so treat it as a hard FLOOR, not a realistic figure.
- V100 PCIe idles at ~27 W (measured via nvidia-smi; the card sits in P0 and does not drop to a low-power state). | state | estimated wall draw | | idle, OS up, GPUs idle | 170-230 W | | typical mixed inference (GPUs busy, CPUs partly loaded) | 500-700 W | | sustained full load (AVX CPU + both V100s at the 200 W cap) | 900-1,050 W | Full-load build-up: 290 W CPUs + 55-65 W for 16 RDIMMs under traffic + 400 W GPUs + 90-140 W board/fans/drives (2U fans alone are 50-100 W at high RPM), then ~88-92% PSU efficiency. RATE: use 16-18 cents/kWh all-in for Xcel MN residential in 2026, and note it is SEASONAL (summer materially higher). Xcel's own published card is $0.13069/kWh summer energy + fuel charge + riders, i.e. not all-in; BLS measured Minneapolis-St Paul at $0.166/kWh in Dec 2024 and $0.20 in Aug-Sep 2024, and the MN PUC approved a further Xcel increase in 2026. Aggregator figures of 15.1-15.8 cents are 2024-era and about 1-2 cents low for now. THE MONTHLY BILL, at 17 cents: | | kWh/month | cost/month | | idle 24/7 (200 W) | 144 | ~$24 | | mixed 24/7 (600 W) | 432 | ~$73 | | hard 24/7 (975 W) | 702 | ~$119 | *** SO: just leaving it on costs about what his entire software budget is, and running it hard costs 3-5x that. This is the honest number, and it should change how overnight batch work is scheduled. *** SETTLE IT FOR ~$20: a plug-in energy meter (Kill A Watt class) on the server's outlet measures real draw and closes THREE open items at once — the electricity-cost item (ADD 4 in jarvis-system-gaps), the UPS sizing below, and the breaker-headroom question in GAP 4. Do this before buying a UPS or planning the 240 V circuit.

## UPS: THE OBVIOUS 900 W UNIT IS UNDERSIZED, AND THE FREE SCHEDULER RULE IS WHAT FIXES THAT

The documented risk is real: a 15 A basement circuit, ~11.4 A uncapped, and a breaker trip mid-write on a single-drive box is exactly the uncontrolled shutdown that the whole nvme-drive-failure saga is about. APC Back-UPS Pro BR1500MS2 — VERIFIED 1500VA / 900 W, pure sine wave, 10x NEMA 5-15R, USB monitoring. Street price $300-340 (B&H $299.99, Newegg 385 first found. *** BUT 900 W CANNOT CARRY THIS MACHINE AT FULL LOAD — the server can exceed the UPS's watt rating outright. For full-load ride-through he needs a 1500 W / 2000 VA class unit. *** THE CHEAPER ANSWER, AND IT IS FREE: GAP 4's mutual-exclusion rule. Never run a GPU video render concurrently with a sustained two-card LLM load. That caps the peak, keeps the machine inside a 900 W UPS, AND removes the breaker-trip scenario. Do the scheduler rule first; buy the UPS second, sized to the metered number. USB CAVEAT on the BR1500MS2: data monitoring comes through an RJ45 jack plus the included RJ45-to-USB cable. The two front USB-A/USB-C ports are CHARGING ONLY. apcupsd support for this exact SKU is unconfirmed; APC BR units generally enumerate as USB HID and work with apcupsd's usb driver or NUT's usbhid-ups.

## *** V100 THERMAL THRESHOLDS, AND A ONE-COMMAND CHECK NOBODY HAS RUN ***

From a real nvidia-smi -q dump on a Tesla V100 (NVIDIA developer forum), all four values confirmed: | field | value | | GPU Max Operating Temp | 83 C | | GPU Slowdown Temp | 87 C | | GPU Shutdown Temp | 90 C | | Memory Max Operating Temp | 85 C | nvidia-smi -q exposes a Clocks Throttle Reasons block with HW Slowdown, HW Thermal Slowdown and SW Thermal Slowdown. THE CHECK, during a long run — thermals have never been examined on this box and passively-cooled V100s in a 2U chassis are exactly where throttling hides:

bash

```bash
nvidia-smi --query-gpu=temperature.gpu,clocks.sm,clocks_throttle_reasons.active --format=csv -l 5
```

If SM clocks sag while temperature approaches 83-87 C, cooling is costing real throughput and no model or quant change will recover it.

## *** llama.cpp HAS CPU-AFFINITY FLAGS AND JACK IS ALMOST CERTAINLY NOT USING THEM. FREE, AND HIS OWN TOPOLOGY DATA SAYS HOW TO SET THEM. ***

Verified against the llama-server manpage: -t/--threads, -tb/--threads-batch, -C/--cpu-mask M (arbitrarily long hex), -Cr/--cpu-range lo-hi, --cpu-strict <0|1> (default 0), --prio N (low -1, normal 0, medium 1, high 2, realtime 3; default 0), --poll <0...100> (default 50), plus -Cb, -Crb, --cpu-strict-batch, --prio-batch (documented 0-3 only, no -1) and --poll-batch (documented <0|1>, NOT 0-100). WHY IT MATTERS HERE SPECIFICALLY: system-performance-levers measured that both V100s sit on NUMA node 0 with CPU affinity 0-17,36-53, and that 18 threads already saturate one socket (36 threads socket-local was slightly SLOWER than 18). So:

- GPU-resident or hybrid slots (the 27B): pin to node 0 with -Cr 0-17 --cpu-strict 1, because host-to-device traffic from node 1 crosses QPI.
- CPU-resident giants: interleave across both sockets, physical cores only, -t 36, never 72.
- --prio 2 and a higher --poll reduce scheduler interference and wake latency on a box that also runs Open WebUI, scrapers and tool servers.

## THE NOVEL EXPERIMENT WORTH RUNNING: DOES HYPERTHREADING HELP PREFILL?

No published benchmark isolates SMT for prompt processing. The community claims ("llama.cpp does not benefit from hyperthreading", discussions #12047 and #3167) are blanket assertions covering both phases with no pp-vs-tg numbers, and Intel's own llama.cpp Xeon study ran with HT OFF, so it cannot answer it either. But Intel's study does confirm the premise: "Prompt processing parallelizes better than token generation across all models. It achieves up to 5.13x speedup, compared with token generation's 4.10x" scaling 4 -> 24 physical cores. Prefill is GEMM-bound rather than bandwidth-bound, which is exactly the regime where SMT usually helps, and llama.cpp provides -tb/--threads-batch precisely so prefill threads can be set independently of decode threads. *** PREFILL IS THE BINDING CONSTRAINT ON EVERY GIANT ON THIS BOX, SO THIS IS A CHEAP SHOT AT THE THING THAT ACTUALLY HURTS: ***

bash

```bash
llama-bench -m <model.gguf> -ngl 0 -p 512 -n 128 -t 36 -tb 36   # baseline
```

\# then sweep -tb 48, 54, 72 and compare the pp512 column only

Minutes to run, and it would be a genuinely new data point that nobody has published.

## AVX FREQUENCY, WHICH SIZES THE CPU-UPGRADE PREFILL GAIN

Sustained AVX2 runs the cores below their rated base. E5-2699 v3: AVX base 1.90 GHz (vs 2.30 nominal), AVX turbo 3.30. E5-2699 v4: AVX base 1.80 GHz, AVX turbo 3.60. Both from Microway's compiled Intel spec-update tables; Intel's own PDFs were unreachable, so these are well-attested secondary, not Intel-primary. CONSEQUENCE FOR THE v4 SWAP in system-performance-levers: raw AVX throughput goes 18 x 1.90 = 34.2 to 22 x 1.80 = 39.6, i.e. +16%, plus roughly 5% Broadwell IPC, so expect ~+20% on PREFILL — not the +22% that core count alone suggests. Decode is bandwidth-bound and gains nothing from the extra cores; its gain comes only from the possible 1866 -> 2133 memory clock.
