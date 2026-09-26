# GLM-5.3-Flash (UD-Q4_K_XL): speed research and runbook

For Simon. Written 2026-09-25/26 (night, Central time). Labels: MEASURED (on jarvis-1, with date), SOURCE (link), ESTIMATE (arithmetic shown), VERIFY (not checked yet; a read-only command is in section E).
Role assumed here: a second-tier big model (Artificial Analysis index 42, between Flash-Next's 40 and GLM-5.3's 45, per the wiki), run on the CPU beside Jarvis when its reasoning is wanted, one big model at a time.
Inputs read: the wiki pages glm-5.3-flash-run-recipe (verified Sep 24), cpu-moe-speed-levers and context-and-speed-per-model; HANDOFF and the benchmark docs (branch claude/new-session-uyo1y3 at 7be739a); the source of Unsloth's fork (branch glm5next/upstream at 86ebfef, 2026-09-16) and ik_llama.cpp at 1aaf7105.
Scripts: `cpu_test.py` and `gguf_bytes.py` from step FN-1 in [qwen3.8-flash-next.md](qwen3.8-flash-next.md) (do FN-1 first if it has not been done).

## A. Current state

**Model** (MEASURED 2026-09-25): unsloth GLM-5.3-Flash UD-Q4_K_XL, 6 shards, 199.71 GB (186.0 GiB) plus an mmproj, copied to `/home/simon/models/GLM-5.3-Flash/` and sha256-verified with big-verify (12:33 PM CT). Exact file path: VERIFY in GF-1.
**Architecture** (SOURCE: [ik PR #2376](https://github.com/ikawrakow/ik_llama.cpp/pull/2376) and the fork's `src/models/glm5next.cpp`): about 18B active parameters (wiki), a hybrid of KDA layers (Kimi-style linear attention with a recurrent state) and MLA layers with a DSA "k-pool" indexer, mHC connections, MoE with 288 experts, and one NextN (MTP) block.
**Quality of this quant** (SOURCE: Unsloth's table, wiki glm-5.3-flash-run-recipe): top-1 92.22%, mean KLD 0.049 vs full precision. Every smaller quant is far worse (UD-IQ3_XXS 81.63% / 0.284).
**Engines**:
- Stock llama.cpp (production f4e276a20 and master 4b1a27f): no `glm5next` architecture. Cannot load this model.
- Unsloth's fork, branch `glm5next/upstream`, head 86ebfef (2026-09-16), mainline merged up to ~Sep 15 (SOURCE: git history). It has the architecture, a real sparse-attention path for the DSA layers (`build_attn_sparse` with the gathered top-k, not a mask), a full MTP draft graph (`graph_mtp`), context checkpoints and recurrent-state rollback for this architecture (SOURCE: the fork's glm5next.cpp, speculative.cpp, server-context.cpp, llama-arch.cpp). Not built on the box yet.
- ik_llama.cpp at 1aaf7105 (built on the box Sep 25): `glm5next` merged Sep 14 ([#2376](https://github.com/ikawrakow/ik_llama.cpp/pull/2376)); its MTP is still an open PR ([#2399](https://github.com/ikawrakow/ik_llama.cpp/pull/2399), needs a rebase); an out-of-memory at ~32K-token prompts is reported in #2376.

**Measured speed on this box: none yet.** Reference points:
- SOURCE ([ik #2399](https://github.com/ikawrakow/ik_llama.cpp/pull/2399)): CPU-only on a 24-thread EPYC 9224 (12-channel DDR5), Q4_K_M: 9.2 t/s decode, 13.2 with MTP n_max 4 (1.43x, 67% acceptance, "output quality verified").
- SOURCE (#2376): single RTX 3090 + CPU: 95.8 t/s prefill, 6.14 decode; 2x 3090 + A4000: ~100 prefill / ~8 decode at 16K context.

**Limits, with arithmetic (ESTIMATE until GF-1 and GF-3 measure them)**
- Bytes per token: 18B active x ~5.0 bits / 8 = ~11.3 GB (wiki arithmetic; GF-1 computes it from the file headers).
- Decode on this box: Flash-Next converted 20-22 GB/s interleaved beside Jarvis; GLM-5.3 converted 36.7 GB/s interleaved with Jarvis stopped (both MEASURED Sep 25). This model's matrices sit between the two, so ~25-35 GB/s / 11.3 GB = **~2-3 t/s** interleaved beside Jarvis; one socket alone ~1.3-1.6 t/s. The wiki's "3-3.5 t/s" is the optimistic end.
- Prefill: 18B active x 2 FLOP = 36 GFLOP per token; at the ~0.8 TFLOPS GLM-5.3 reached (MEASURED 10 t/s x 80 GFLOP), ~20 t/s at depth 0.
- RAM: 186 GiB resident; fits one socket (251 GiB) with room, and a mirror (2 x 186 = 372 GiB) fits the box at full Q4 quality. The KDA layers carry a recurrent state, so prompt reuse depends on context checkpoints, like Flash-Next (the wiki flags this as the highest-risk item for agent use).

## B. Levers, ranked

| # | Lever | Expected gain | Quality risk | Downtime? | Effort | Evidence |
|---|---|---|---|---|---|---|
| 1 | **Build the Unsloth fork** (the only engine with architecture + MTP today) | enables the model at all | none | no | GF-2 | fork branch `glm5next/upstream` (SOURCE above; Unsloth's run guide via the wiki). Mainline draft PRs #27752/#27754 are not the route (wiki, verified Sep 24) |
| 2 | **Prompt-cache reuse** (context checkpoints) | follow-up requests re-read ~10-100 tokens instead of the whole prompt: ~2 min saved per 2,500 re-read tokens at ~20 t/s (ESTIMATE) | none | no | GF-3 (cache test) | the fork's server has the checkpoint logic of mainline PR [#20288](https://github.com/ggml-org/llama.cpp/pull/20288) and rs_rollback lists GLM5NEXT (SOURCE). VERIFY on the box: KDA hybrids are the high-risk case |
| 3 | **MTP with the built-in NextN head** (`--spec-type draft-mtp`, no draft file) | ESTIMATE 1.3-1.5x decode | output may differ at a near-tie token (check) | no | GF-4 | SOURCE ik #2399: 1.43x CPU-only at n_max 4; MEASURED on this box for Flash-Next: 1.57x at n-max 3 |
| 4 | **Both sockets interleaved** (numactl --interleave=all) | ESTIMATE +20-30% decode, +50-60% prefill over one socket | none | no | GF-3 baseline uses it | MEASURED for Flash-Next Sep 25: +28% decode, +60% prefill, Jarvis -3% median |
| 5 | **NUMA mirror** (ik PR #2396 tree from Flash-Next FN-7) | ESTIMATE +10-20% over interleave | none expected; check | no | GF-6 | SOURCE: +15.1% on 2x Broadwell for Flash-Next ([ik #2396](https://github.com/ikawrakow/ik_llama.cpp/pull/2396)); this model at full Q4 fits twice in RAM (the wiki calls this "the lucky part"). ik has glm5next but not its MTP yet, so mirror and MTP cannot be combined today |
| 6 | **ik_llama.cpp** as the engine | ESTIMATE prefill +20-100%, decode ±10%; no MTP until #2399 merges | different kernels; check | no | GF-5 | ik's CPU kernels (see the GLM-5.3 file's correction on the #164 citation: big prefill gains, small decode gains) |
| 7 | **Save/restore a long context** (`--slot-save-path`) | ESTIMATE: re-reading a long document becomes a file load | same answer after restore required | no | GF-3 (slot test) | for this hybrid model the restored state is the end of the saved tokens and has no checkpoints, so a re-sent prompt may be re-read in full (ESTIMATE from the server code; the test measures it) |
| 8 | GPU hybrid in a Jarvis-off window | ESTIMATE decode ~2x, prefill ~5x (source users on 3090s: ~95-100 t/s prefill, 6-8 decode) | none | **yes (SIMON ONLY)** and a CUDA build of the fork with `-DCMAKE_CUDA_ARCHITECTURES=70` | not scheduled | #2376 numbers above. Only worth it if Simon accepts Jarvis-off windows for this model |
| 9 | Shorter reasoning (`reasoning_effort` low/high/max) | ESTIMATE 2-5x less wall time on easy tasks | **lossy**: needs equal scores on Simon's quality suite | no | orchestrator setting | Unsloth's run line uses "max" (wiki). At 2-3 t/s, "max" is very slow |
| - | Smaller quants | faster | **fail the gate by far** (UD-IQ3_XXS KLD 0.284 vs 0.049 for Q4; gate <= 0.01 vs Q4) | - | not scheduled | Unsloth table (wiki) |
| - | Does **not** apply | | | | | stock/mainline llama.cpp (no architecture); tensor parallel (CPU model); K cache q8_0 (no speed gain on CPU); `-b/-ub 4096` "2x prefill" (MEASURED flat or worse on CPU for GLM-5.3 and Flash-Next); PrismML NUMA repack PR (dense matmuls only); `--load-mode none` (a CUDA long-context OOM workaround, irrelevant on CPU; `-lm dio` already reads the weights into RAM) |

Hardware: same list as the GLM-5.3 file (v4 CPUs +14% bandwidth; a GPU that is not Jarvis's for lever 8). 1 TB RAM is not needed for this model's mirror.

## C. Runbook

Order: facts, build, baseline with reference (cache and slot tests), MTP, the ik engine, the mirror, then SIMON ONLY adoption. One lever per step. Tests run as the unit `cpu-test` (harness `cpu_test.py`, CPU only, port 8082, beside Jarvis; it refuses to start when another benchmark unit runs or RAM is short and stops itself if Jarvis slows below 75% twice).
The model path used below is `/home/simon/models/GLM-5.3-Flash/UD-Q4_K_XL/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf`. GF-1 checks it; if GF-1 finds a different first-shard path, use that one everywhere instead.
Before every step this must print NONE-ACTIVE:
`systemctl list-units --type=service --state=active --no-legend --plain | grep -E '^(bench-|mtp-test|il-beside|glm-test|fn-test|t27-|big-verify|build-|dl-|kld-|cpu-test)' || echo NONE-ACTIVE`

```text
JARVIS STEP GF-1 of 8: record the starting point (read-only)
Goal: the exact model path, bytes per token, the layer mix (KDA vs attention), the MTP block, and free RAM.
Precondition: Flash-Next FN-1 done: ls ~/speed/scripts/cpu_test.py ~/speed/scripts/gguf_bytes.py
Commands (one at a time; all read-only):
 1) the NONE-ACTIVE check above
 2) find ~/models/GLM-5.3-Flash -name '*.gguf' -printf '%s %p\n' | sort -k2 | cut -c1-160
 3) python3 ~/speed/scripts/gguf_bytes.py /home/simon/models/GLM-5.3-Flash/UD-Q4_K_XL/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf
 4) python3 -c "import sys; sys.path.insert(0, '/home/simon/speed/scripts'); import gguf_bytes as g; kv, _ = g.parse('/home/simon/models/GLM-5.3-Flash/UD-Q4_K_XL/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf'); print({k: v for k, v in kv.items() if any(x in k for x in ('kda', 'indexer', 'nextn', 'expert', 'block_count', 'ssm', 'context_length'))})"
 5) grep MemAvailable /proc/meminfo; ps -eo rss,args --sort=-rss | head -3 | cut -c1-150
Takes: 2 minutes.
Expected: 2 lists 6 shards of the UD-Q4_K_XL files (plus an mmproj) adding up to ~199.7 GB; if the first shard's path differs from the one above, use the printed path in every later step. 3 prints the per-token estimate (ESTIMATE ~11 GB) and the routed-expert share. 4 prints the KDA/indexer settings, nextn_predict_layers 1, expert count 288. 5 MemAvailable at least 215,000,000 kB and no other big model resident.
PASS: 2, 3 and 4 printed. If another big model is resident, stop (one big model at a time).
Undo: nothing (read-only).
save_finding(topic="speed-glm53flash", finding="GF-1: path _, per-token _ GB (experts _%), layers _, KDA _, nextn _, experts _/_, MemAvailable _ GiB", source="gguf_bytes.py")
```

```text
JARVIS STEP GF-2 of 8: build Unsloth's glm5next fork (CPU-only) in its own folder
Goal: an engine that runs this model with MTP. New folder ~/llama.cpp-glm5next, pinned to the fork commit read for this runbook; production ~/llama.cpp is not touched.
Preconditions (read-only): NONE-ACTIVE; ls -d ~/llama.cpp-glm5next 2>&1 | tail -1 says "No such file or directory"; df -h --output=avail /home | tail -1 shows at least 5G.
Commands:
 1) git init -q ~/llama.cpp-glm5next && git -C ~/llama.cpp-glm5next fetch -q --depth 1 https://github.com/unslothai/llama.cpp 86ebfef2c6a0f3359a2a07d2c215d61b0fa885c9 && git -C ~/llama.cpp-glm5next checkout -q FETCH_HEAD && git -C ~/llama.cpp-glm5next log -1 --format='%h %ad %s' --date=short
    Expected: 86ebfef 2026-09-16 glm5next: avoid soft_max gridDim.y overflow in the indexer (#214)
    If the fetch fails (the branch was rewritten): git -C ~/llama.cpp-glm5next fetch -q --depth 1 https://github.com/unslothai/llama.cpp glm5next/upstream && git -C ~/llama.cpp-glm5next checkout -q FETCH_HEAD, and record the new hash.
 2) sudo systemd-run --unit=build-glm5next -p User=simon -p Group=simon -p Nice=10 -p WorkingDirectory=/home/simon/llama.cpp-glm5next /bin/bash -c 'cmake -S . -B build -DGGML_CUDA=OFF -DGGML_NATIVE=ON -DCMAKE_BUILD_TYPE=Release >cfg.log 2>&1 && cmake --build build -j 36 --target llama-server llama-bench >build.log 2>&1'
 3) when systemctl is-active build-glm5next prints inactive or failed: tail -2 ~/llama.cpp-glm5next/build.log | cut -c1-200; ls -l ~/llama.cpp-glm5next/build/bin/llama-server
Takes: fetch ~1 min, build ~15-25 min.
Expected: "[100%] Built target llama-server" and the binary listed.
PASS: the binary exists. FAIL: tail -20 ~/llama.cpp-glm5next/build.log | cut -c1-200 and tell Claude; clear a failed unit with sudo systemctl reset-failed build-glm5next.
Undo: rm -rf ~/llama.cpp-glm5next (Simon's yes).
save_finding(topic="speed-glm53flash", finding="GF-2 fork built at _ (CPU-only), ok _", source="~/llama.cpp-glm5next/build.log")
```

```text
JARVIS STEP GF-3 of 8: first measurement beside Jarvis + reference + prompt cache + slot restore
Goal: the first numbers for this model on the box (both sockets interleaved, -t 18 -tb 36), a greedy reference with a run-to-run identity check, whether follow-up requests reuse the prompt (KDA hybrid = high risk), and whether a slot file avoids a re-read.
Preconditions (read-only): GF-1 and GF-2 PASS; NONE-ACTIVE; then
 python3 ~/speed/scripts/cpu_test.py glmf-il --bin /home/simon/llama.cpp-glm5next/build/bin/llama-server --model /home/simon/models/GLM-5.3-Flash/UD-Q4_K_XL/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf --numa il --make-ref glmf-ref --tests speed,prefill,cache,slot --max-min 230 --check -- -lm dio -lzm off -t 18 -tb 36 -lv 4 --slot-save-path /home/simon/speed/slots
 must end with: CHECK OK (nothing started)
Command: the same line without --check, started as a unit:
 sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=230G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=14400 -p TimeoutStopSec=300 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py glmf-il --bin /home/simon/llama.cpp-glm5next/build/bin/llama-server --model /home/simon/models/GLM-5.3-Flash/UD-Q4_K_XL/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf --numa il --make-ref glmf-ref --tests speed,prefill,cache,slot --max-min 230 -- -lm dio -lzm off -t 18 -tb 36 -lv 4 --slot-save-path /home/simon/speed/slots
Watch: journalctl -u cpu-test -n 12 --no-pager -o cat | cut -c1-200
Read: D=$(ls -d ~/speed/results/cpu/glmf-il/2* | tail -1); grep -v '^command' $D/summary.txt
Takes: ~45-75 min.
Expected (ESTIMATE): decode ~2-3 t/s, prefill ~15-20 t/s; "reference re-run identical: 3/3 | saved as reference glmf-ref"; Jarvis within 10% of its normal speed.
PASS: re-run identical 3/3 AND reference saved AND Jarvis during >= 90% of before AND no STOPPED/ERROR line.
Findings either way: the prompt-cache line (FAIL = each follow-up re-reads the whole prompt) and the slot line; tell Simon about a FAIL before any adoption.
FAIL (server did not start): tail -5 of $D/server.log; tell Claude.
Undo: nothing (results in ~/speed/results/cpu; the slot file is overwritten by each run).
save_finding(topic="speed-glm53flash", finding="GF-3 fork il: decode _/_/_ mean _, prefill _, rerun _/3, cache _ (turns _, ckpt _ MiB), slot _, load _ s, RSS _ GiB, Jarvis _ -> _", source="~/speed/results/cpu/glmf-il/<time>/summary.txt")
```

```text
JARVIS STEP GF-4 of 8: MTP with the model's NextN head (fork)
Goal: speculative decoding with the built-in head, n-max 2 and 3; n-max 4 only if 3 beats 2.
Preconditions: GF-3 PASS; NONE-ACTIVE.
Run one at a time:
 A) sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=230G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=14400 -p TimeoutStopSec=300 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py glmf-mtp2 --bin /home/simon/llama.cpp-glm5next/build/bin/llama-server --model /home/simon/models/GLM-5.3-Flash/UD-Q4_K_XL/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf --numa il --ref glmf-ref --tests speed --max-min 230 -- -lm dio -lzm off -t 18 -tb 36 --spec-type draft-mtp --spec-draft-n-max 2
 B) the A command with label glmf-mtp3 and --spec-draft-n-max 3
 C) only if B beats A: label glmf-mtp4 and --spec-draft-n-max 4
Read: for L in glmf-mtp2 glmf-mtp3 glmf-mtp4; do D=$(ls -d ~/speed/results/cpu/$L/2* 2>/dev/null | tail -1); [ -n "$D" ] && echo "== $L" && grep -E '^(load|decode|vs ref|Jarvis|STOP|ERROR)' $D/summary.txt; done
Takes: ~30-45 min each.
Expected: 1.3-1.5x the GF-3 decode mean (ESTIMATE; SOURCE ik #2399 1.43x on CPU); acceptance ~0.6-0.8; each prompt IDENTICAL or NEAR-TIE.
PASS: best mean >= 1.25 x GF-3 AND every prompt IDENTICAL or NEAR-TIE (gap <= 0.10) AND Jarvis during >= 85% of before.
FAIL: DIVERGED (gap above 0.10) = MTP changes answers: do not adopt; tell Simon. A run that does not start: tail -5 of its server.log.
Undo: nothing (test units only).
save_finding(topic="speed-glm53flash", finding="GF-4 MTP: n2 _ (acc _), n3 _ (acc _), n4 _; best x_ vs GF-3; vs ref _ gap _ -> PASS/FAIL", source="~/speed/results/cpu/glmf-mtp*/<time>/summary.txt")
```

```text
JARVIS STEP GF-5 of 8: ik_llama.cpp as the engine (no MTP yet)
Goal: compare ik's kernels on this model: decode, prefill, prompt cache. ik's MTP for this architecture is still an open PR, so this is without MTP.
Preconditions (read-only): GF-3 PASS; NONE-ACTIVE; ls -l ~/ik_llama.cpp/build/bin/llama-server
Command:
 sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=230G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=14400 -p TimeoutStopSec=300 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py glmf-ik --bin ik --model /home/simon/models/GLM-5.3-Flash/UD-Q4_K_XL/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf --numa il --ref glmf-ref --tests speed,prefill,cache --max-min 230 -- --no-mmap -t 18 -tb 36
Read: D=$(ls -d ~/speed/results/cpu/glmf-ik/2* | tail -1); grep -E '^(load|decode|vs ref|prefill|prompt cache|Jarvis|STOP|ERROR)' $D/summary.txt
If it did not start: tail -5 $D/server.log | cut -c1-200
Takes: ~45-60 min.
Expected (ESTIMATE): decode within 10% of GF-3, prefill 1.2-2x GF-3; prompts IDENTICAL or NEAR-TIE; ik prints no checkpoint lines, so judge its cache line by the token counts.
PASS: (decode >= 1.05 x GF-3 OR prefill >= 1.2 x GF-3) AND every prompt IDENTICAL or NEAR-TIE AND Jarvis during >= 90% of before. Even on PASS, the fork with MTP (GF-4) may still be faster overall: compare GF-4's best with this.
Undo: nothing.
save_finding(topic="speed-glm53flash", finding="GF-5 ik: decode _ (x_), prefill _ (x_), vs ref _, cache _ -> PASS/FAIL", source="~/speed/results/cpu/glmf-ik/<time>/summary.txt")
```

```text
JARVIS STEP GF-6 of 8: NUMA mirror (ik tree from Flash-Next FN-7)
Goal: one copy of the weights per socket (2 x 186 GiB), so every thread reads local memory. Only possible with ik (no MTP for this model there yet).
Preconditions (read-only): Flash-Next FN-7 PASS (ls -l ~/ik-mirror/build/bin/llama-server); GF-5 started fine (ik loads this model); NONE-ACTIVE; grep MemAvailable /proc/meminfo at least 410,000,000 kB; cat /proc/sys/kernel/numa_balancing prints 0.
Command (never add --no-mmap here: the mirror needs mmap):
 sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=400G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 -p RuntimeMaxSec=14400 -p TimeoutStopSec=300 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py glmf-mirror --bin ikmirror --model /home/simon/models/GLM-5.3-Flash/UD-Q4_K_XL/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf --numa none --ref glmf-ref --tests speed,prefill --max-min 230 -- -t 36 -tb 36 --numa mirror
Read: D=$(ls -d ~/speed/results/cpu/glmf-mirror/2* | tail -1); grep -E '^(load|decode|vs ref|prefill|Jarvis|STOP|ERROR)' $D/summary.txt
Takes: ~45-60 min.
Expected (ESTIMATE): per-node MB ~190,000+ on each node; decode +10-20% over the better of GF-3/GF-5 (SOURCE ik #2396: +15% on 2x Broadwell for a sibling model).
PASS: decode >= 1.1 x the better of GF-3 and GF-5 AND every prompt IDENTICAL or NEAR-TIE AND Jarvis during >= 90% of before. Weigh it against GF-4: MTP on the fork may beat the mirror without MTP.
Undo: nothing.
save_finding(topic="speed-glm53flash", finding="GF-6 mirror: decode _ (x_ vs best non-mirror), prefill _, nodes _, vs ref _, Jarvis _ -> PASS/FAIL", source="~/speed/results/cpu/glmf-mirror/<time>/summary.txt")
```

```text
JARVIS STEP GF-7 of 8: SIMON ONLY - Jarvis must not run this. A GLM-5.3-Flash job server started when needed
Why SIMON ONLY: a new systemd unit that holds ~186 GiB (or ~372 GiB mirrored) of RAM while it runs.
Goal: one unit with the winning variant, NOT started at boot, on the shared big-model port 8081 (only one big model runs at a time).
Preconditions (read-only): GF-3 PASS including the prompt-cache line; the chosen variant PASSED (GF-4, GF-5 or GF-6); NONE-ACTIVE; systemctl is-active flash-next glm-jobs prints inactive twice.
Commands (Simon):
 1) sudo tee /etc/systemd/system/glm-flash.service >/dev/null <<'UNIT_END'   then paste the unit text from section D (ExecStart for the variant that won), then a line UNIT_END
 2) sudo systemctl daemon-reload && sudo systemctl start glm-flash
 3) for i in $(seq 60); do curl -sf localhost:8081/health && break; sleep 10; done
 4) curl -s localhost:8081/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"Say OK."}],"max_tokens":200,"chat_template_kwargs":{"reasoning_effort":"low"}}' | python3 -c "import json,sys;r=json.load(sys.stdin);print(r['choices'][0]['message'].get('content'),r['timings']['predicted_per_second'])"
 5) curl -s localhost:8080/health    (Jarvis still answers)
 6) when finished: sudo systemctl stop glm-flash    (do not enable it at boot)
PASS: 3, 4 and 5 succeed. FAIL: journalctl -u glm-flash -n 30 --no-pager, then the rollback.
Rollback: sudo systemctl stop glm-flash && sudo mv /etc/systemd/system/glm-flash.service ~/speed/glm-flash.service.off && sudo systemctl daemon-reload
save_finding(topic="speed-glm53flash", finding="GF-7 glm-flash unit with variant _, probe _ t/s", source="systemctl status glm-flash")
```

```text
JARVIS STEP GF-8 of 8: check real jobs afterwards (read-only)
Precondition: glm-flash has served real jobs since GF-7.
Commands:
 1) journalctl -u glm-flash --since "-7d" -o cat --no-pager | python3 ~/speed/scripts/j27_logstats.py
 2) journalctl -u glm-flash --since "-7d" -o cat --no-pager | grep -c -E 'GGML_ASSERT|ggml_abort|out of memory|Segmentation'
Takes: 1 minute.
Expected: decode and prompt-eval percentiles (for an ik unit j27_logstats.py may parse nothing: then journalctl -u glm-flash -n 30); 2 prints 0.
PASS: token-weighted decode >= 0.9 x the winning step's decode AND 2 prints 0 AND prompt-eval p50 in seconds (the cache works). FAIL: tell Simon; rollback in GF-7.
Undo: nothing (read-only).
save_finding(topic="speed-glm53flash", finding="GF-8 real jobs: decode p50 _ weighted _, prompt-eval p50 _ ms, crash lines _ -> PASS/FAIL", source="journalctl glm-flash 7d")
```

## D. Proposed final config (PROPOSED until GF-3..GF-6 measure it)

Default = the fork with MTP, both sockets interleaved (the combination with the most evidence behind it). ESTIMATE ~2-3 t/s x 1.3-1.5 = ~2.6-4.5 t/s decode, ~15-20 t/s prefill, beside Jarvis.

```ini
[Unit]
Description=GLM-5.3-Flash job server (llama-server on 127.0.0.1:8081, start by hand, one big model at a time)
After=network-online.target llama-server.service

[Service]
User=simon
Group=simon
Environment=CUDA_VISIBLE_DEVICES=
ExecStart=/usr/bin/numactl --interleave=all /home/simon/llama.cpp-glm5next/build/bin/llama-server -m /home/simon/models/GLM-5.3-Flash/UD-Q4_K_XL/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf -lm dio -lzm off -t 18 -tb 36 -c 65536 --parallel 1 --jinja --host 127.0.0.1 --port 8081 --spec-type draft-mtp --spec-draft-n-max 3 --slot-save-path /home/simon/speed/slots
MemoryMax=230G
MemorySwapMax=0
OOMScoreAdjust=500
Nice=5
```

(No `[Install]` section: never started at boot.) Use the n-max that won GF-4; drop the two MTP flags if GF-4 failed. If the mirror won GF-6 and MTP failed GF-4: `ExecStart=/home/simon/ik-mirror/build/bin/llama-server -m <same model> -t 36 -tb 36 --numa mirror -c 65536 --parallel 1 --jinja --host 127.0.0.1 --port 8081` with `MemoryMax=400G`.
Sampling: Unsloth recommends temperature 1.0, top_p 0.95 for this model (wiki), set per request by the client. MTP gains shrink at higher temperature (MEASURED for the 27B: 51 / 42 / 41 t/s at temperature 0 / 0.3 / 0.8), so expect the low end of the MTP range in real use.

## E. Open questions and VERIFY items (each with a read-only command)

1. The model path, bytes per token, layer mix and NextN block: GF-1 commands 2-4.
2. Has Unsloth's branch moved past 86ebfef (fixes worth taking)? `git ls-remote https://github.com/unslothai/llama.cpp refs/heads/glm5next/upstream` (read-only network query).
3. Has ik merged glm5next MTP ([#2399](https://github.com/ikawrakow/ik_llama.cpp/pull/2399))? Check the PR page; if merged, a mirror + MTP combination becomes possible in one ik build.
4. ik's reported out-of-memory at ~32K-token prompts (#2376): if GF-5 passes and long prompts matter, test one with the harness's `--prefill-lines 1200` (~32K tokens) before adopting ik.
5. Does the fork's sparse attention run on the CPU backend, or fall back to the masked path? There is no read-only check; the practical check is a test run: GF-3's command with label glmf-16k and `--tests prefill --prefill-lines 600` (a ~16K document), compared with GF-3's ~5K figure (a small drop = sparse works).
