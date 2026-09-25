#!/bin/bash
# Bundles everything from the benchmark runs into one text file to paste to Claude.
# Usage: ~/bench/report.sh [label-prefix]     e.g. ~/bench/report.sh glm
B=/home/simon/bench
OUT=$B/report-$(date -u +%Y%m%d-%H%M).txt
{
  echo "===== SYSTEM $(date -u '+%F %T')Z"
  (cd /home/simon/llama.cpp && git log -1 --format='llama.cpp %h %cd' --date=short)
  free -g | head -2
  numactl -H | grep -E 'node [01] (size|free)'
  echo "THP: $(cat /sys/kernel/mm/transparent_hugepage/enabled)"
  echo "numa_balancing: $(cat /proc/sys/kernel/numa_balancing)  governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)"
  nvidia-smi --query-gpu=index,memory.used,temperature.gpu --format=csv,noheader
  echo "Jarvis: $(systemctl is-active llama-server)"
  echo; echo "===== QUEUE LOG"; tail -60 $B/queue.log 2>/dev/null
  echo "done: $(tr '\n' ' ' < $B/queue.done 2>/dev/null)"
  echo "failed: $(tr '\n' ' ' < $B/queue.failed 2>/dev/null)"
  for d in $B/results/${1:-}*/; do
    [ -d "$d" ] || continue
    echo; echo "===== TEST $(basename "$d")"
    for a in "$d"*.args; do echo "args: $(cat "$a")"; done
    python3 $B/summary.py "$d"*.jsonl 2>&1
    echo "--- log highlights"
    grep -hiE 'KV|kv_cache|buffer size|load time|model size|n_ctx|error|fail|abort|out of memory|oom|unsupported|not supported|terminate' "$d"*.log 2>/dev/null | cut -c1-200 | sort -u | tail -25
    echo "--- log tail"
    tail -3 "$d"*.log 2>/dev/null | cut -c1-200
  done
} > "$OUT" 2>&1
echo "$OUT  ($(wc -l < "$OUT") lines, $(wc -c < "$OUT") bytes)"
