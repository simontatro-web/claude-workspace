# Jarvis briefing — PART 5: verified on the box (survey of 2026-09-25 01:00 UTC)

Companion to briefing-2026-09-25.md and part4. Written by Claude from Simon's run of ~/jarvis-survey.sh. Where this part disagrees with Parts 1-4, THIS PART WINS for anything marked LIVE.

## LIVE — confirmed on the box
- Services running: llama-server, jarvis-run-host-commands (tool server), gpu-tune (exited = applied), jarvis-perf (exited = applied), nvidia-persistenced. nvidia-powercap is present but inactive, as intended.
- The whole pre-rebuild stack is GONE: no jarvis-api/worker/notify/health units, nothing listening on 8110, 8100, 8102, 8103 or 8090. The job queue, ntfy notifier, healthcheck, supervisor, embedding server and ACT tool server all need rebuilding before anything depends on them.
- Listening on all interfaces: 22 (ssh), 3000 (Open WebUI), 8080 (llama-server), 8200 (tool server), 111 (rpcbind).
- llama-server ExecStart starts with /usr/bin/numactl --cpunodebind=0 --membind=0 (confirmed).
- Tool server ExecStart: uvicorn main:app --host 0.0.0.0 --port 8200 — the unrestricted shell IS exposed to the LAN. Fix remains: --host 172.17.0.1 (Simon's decision).
- GPUs: driver 580.178.04, ECC DISABLED on both, power limit 200 W. VRAM at the time: GPU0 13,914 MiB, GPU1 14,130 MiB.
- NVIDIA driver is NOT held (apt-mark showhold is empty). An unattended upgrade could break the CUDA stack. Pinning it is Simon's decision.
- nvidia-smi shows "CUDA 13.0" — that is only the newest CUDA the DRIVER supports. The toolkit used to build llama.cpp is 12.9 and must stay 12.9 or older (13.x cannot compile for sm_70). Do not read the 13.0 as the toolkit.
- Tuning: numa_balancing=0, governor=performance, jarvis-perf active.
- llama.cpp build supports: qwen4exp (Flash-Next) YES, glm-dsa (GLM-5.3 full) YES, hy_v4 YES, mimo2 (MiMo) YES, deepseek4 YES, glm5next (GLM-5.3-Flash) NO → Flash still needs the Unsloth fork.
- Tailscale: "No serve config" — nothing is published through tailscale serve or Funnel. Nothing is exposed to the internet that way.
- Open WebUI: port 3000 answers 200. The jarvis model row: temperature 0, num_ctx 24576, function_calling native, builtin_tools False (all as intended).
- SYSTEM PROMPT: only 367 characters, and sections 13/14/19 are ABSENT. Your safety rules currently live only in ~/jarvis-memory/operating-manual.md, which you must choose to read. Simon is adding them to the system prompt.
- Boot drive (990 PRO) SMART: critical_warning 0, available_spare 100%, percentage_used 0%, media_errors 0. Healthy. The old spare-pool worries were about the previous drive.
- Context overflow: 1 "truncated = 1" event since the last boot — one chat hit the 24,576 window and silently lost history.
- Your plugins: gpu_status, memory_search, sys_summary.

## Hardware identity — conflict to settle
- Your own finding (Sep 22) says jarvis-1 is a HYVE G2GPU12 GPU server on an ASUS Z10PG-D16 board, and that Simon's ASUS ESC4000 G3 is a SEPARATE machine being set up as a NAS (8 hot-swap 3.5" bays, arrived without caddies; correct caddy part ASUS 13GS1I0AM063-1). Claude's notes call jarvis-1 an "ESC4000 G3" throughout. The board and CPUs are the same either way, but chassis-specific facts in Claude's notes (PSU derating, the proprietary GPU power harness, "max 4 GPUs", ASUS's ESC4000 CPU support list and BIOS versions) may NOT apply to jarvis-1. VERIFY with: sudo dmidecode -s system-product-name; sudo dmidecode -s baseboard-product-name; sudo dmidecode -s bios-version.
- Storage on jarvis-1: Samsung 990 PRO 1 TB NVMe (OS) plus a SATA optical drive; about 9 onboard SATA ports are free.
- The NAS is the natural OFF-BOX target for the WANT 19 backup.

## Your memory system (so both halves get used)
- Files: state.md (snapshot), log.md (dated actions), operating-manual.md (your rules), and findings/<topic>.md written by save_finding and read by memory_search.
- state.md is STALE: its serving section is the Sep 21 config (q8_0 KV, -c 32768, -devd CUDA1, --parallel 1). The live config is the one in Part 1 of the briefing (f16 KV, -c 24576, -ts 28,36, -devd CUDA0, --parallel 2, --kv-unified, xhigh, p-min 0.4, numactl node 0). Update state.md from the briefing when Simon asks.
- Known failure: a fresh chat may never call memory_search. Simon is adding a system-prompt line telling you to call it at the start of every conversation.
- The system prompt IS on jarvis-1 — it lives in Open WebUI's database inside the open-webui container — but you cannot edit it (docker needs sudo). Only Simon edits it, through the Open WebUI model editor.
- The user is Simon. Older notes call him Jack; treat them as the same person and use "Simon".

## Corrections to your own findings
- Kimi K3: Claude's sources give the smallest documented quant as UD-IQ1_S at 594 GB (needs ~610 GB RAM). Lower-bit TQ1_0/Q1_0 files exist in the repo but have no published quality numbers. Either way it does not fit this box usefully.

END OF PART 5
