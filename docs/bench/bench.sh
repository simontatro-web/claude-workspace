#!/bin/bash
# Runs one llama-bench sweep as a transient systemd unit, so a dropped SSH session cannot stop it.
# Usage: ~/bench/bench.sh <label> <profile> <llama-bench args...>
# Profiles:
#   cpu1   socket 1 only (CPUs and memory), GPUs hidden. Safe beside Jarvis.
#   cpu    both sockets, fill socket 1 first, GPUs hidden. Safe beside Jarvis.
#   cpuil  both sockets interleaved, GPUs hidden. Needs Jarvis STOPPED.
#   gpu    GPUs visible, CPU memory interleaved. Needs Jarvis STOPPED.
# Results: ~/bench/results/<label>/<time>.jsonl (one line per test), log alongside.
# Watch:  journalctl -u bench-<label> -f      Stop: sudo systemctl stop bench-<label>
set -u
LABEL="${1:-}"; PROFILE="${2:-}"
[[ "$LABEL" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "label must be letters, digits, _ . - only"; exit 1; }
shift 2 || { echo "usage: bench.sh <label> <profile> <llama-bench args...>"; exit 1; }
[ $# -gt 0 ] || { echo "no llama-bench arguments given"; exit 1; }
BIN=/home/simon/llama.cpp/build/bin/llama-bench
MEMMAX="${MEMMAX:-465G}"
ENVS=(-E CUDA_VISIBLE_DEVICES=)
case "$PROFILE" in
  cpu1)  NUMA=(--cpunodebind=1 --membind=1) ;;
  cpu)   NUMA=(--preferred=1) ;;
  cpuil) NUMA=(--interleave=all) ;;
  gpu)   NUMA=(--interleave=all); ENVS=() ;;
  *) echo "unknown profile: $PROFILE"; exit 1 ;;
esac
if [[ "$PROFILE" == cpuil || "$PROFILE" == gpu ]] && systemctl is-active --quiet llama-server; then
  echo "profile $PROFILE needs Jarvis stopped first: sudo systemctl stop llama-server"; exit 1
fi
if systemctl is-active --quiet "bench-$LABEL"; then echo "bench-$LABEL is already running"; exit 1; fi
sudo systemctl reset-failed "bench-$LABEL" 2>/dev/null
OUT=/home/simon/bench/results/$LABEL
mkdir -p "$OUT"
TS=$(date -u +%Y%m%d-%H%M%S)
printf '%s\n' "$*" > "$OUT/$TS.args"
sudo systemd-run --unit="bench-$LABEL" --description="llama-bench $LABEL ($PROFILE)" \
  -p User=simon -p Group=simon \
  -p MemoryMax="$MEMMAX" -p MemorySwapMax=0 -p OOMScoreAdjust=1000 \
  -p StandardOutput=append:"$OUT/$TS.jsonl" -p StandardError=append:"$OUT/$TS.log" \
  "${ENVS[@]}" \
  /usr/bin/numactl "${NUMA[@]}" "$BIN" -o jsonl "$@"
echo "started bench-$LABEL ($PROFILE). Results: $OUT/$TS.jsonl"
