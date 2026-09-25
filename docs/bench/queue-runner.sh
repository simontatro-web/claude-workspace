#!/bin/bash
# Overnight benchmark queue. Runs the jobs in ~/bench/queue.txt one at a time.
# Start:  sudo systemd-run --unit=bench-queue --collect -p TimeoutStopSec=900 /home/simon/bench/queue-runner.sh
# Pause:  touch ~/bench/STOP   (finishes the current job, then stops cleanly)
# Status: tail -20 ~/bench/queue.log
# Queue line format:  <label> <profile> <max-hours> <llama-bench args...>
#   profiles: cpu1, cpu (safe beside Jarvis); cpuil, gpu (need Jarvis stopped)
# Jarvis is only stopped inside the night window below, never longer than MAX_OFF_MIN,
# and is always started again at the end, even if this script fails or is stopped.
set -u
B=/home/simon/bench
Q=${BENCH_QUEUE:-$B/queue.txt}; DONE=$B/queue.done; FAILED=$B/queue.failed; LOG=$B/queue.log; STOP=$B/STOP
BIN=${BENCH_BIN:-/home/simon/llama.cpp/build/bin/llama-bench}; OUTFMT=${BENCH_OUT:-jsonl}
TZNAME=America/Chicago
WIN_START=1; WIN_END=7        # local hours when Jarvis may be stopped
MAX_OFF_MIN=300               # longest Jarvis may be down in one night
MEMMAX=465G
touch "$DONE" "$FAILED"; chown simon:simon "$DONE" "$FAILED" "$LOG" 2>/dev/null

log() { echo "$(date -u '+%F %T')Z  $*" >> "$LOG"; }
notify() {
  log "NOTIFY: $*"
  if [ -s /home/simon/.ntfy-topic ]; then
    curl -s -m 10 -d "$*" "https://ntfy.sh/$(head -1 /home/simon/.ntfy-topic)" >/dev/null || true
  fi
}
jarvis_ok() { curl -s -m 5 http://127.0.0.1:8080/health | grep -q '"ok"'; }
in_window() {
  local h; h=$(TZ=$TZNAME date +%-H)
  [ "$h" -ge "$WIN_START" ] && [ "$h" -lt "$WIN_END" ]
}

WE_STOPPED=0; OFF_SINCE=0; OFF_USED=0; NO_OFF=0; CUR_UNIT=""
off_minutes() {  # total minutes Jarvis has been down tonight, including now
  local now=0
  [ "$WE_STOPPED" -eq 1 ] && now=$(( ($(date +%s) - OFF_SINCE) / 60 ))
  echo $(( OFF_USED + now ))
}
stop_jarvis() {
  [ "$WE_STOPPED" -eq 1 ] && return 0
  log "stopping Jarvis (llama-server) for GPU/interleaved jobs"
  systemctl stop llama-server && WE_STOPPED=1 && OFF_SINCE=$(date +%s)
}
start_jarvis() {
  [ "$WE_STOPPED" -eq 1 ] || return 0
  OFF_USED=$(off_minutes)
  log "starting Jarvis (llama-server), down ${OFF_USED} min so far tonight"
  systemctl start llama-server
  for i in $(seq 1 30); do sleep 10; if jarvis_ok; then log "Jarvis healthy"; WE_STOPPED=0; return 0; fi; done
  log "Jarvis not healthy after 300 s, trying one restart"
  systemctl restart llama-server
  for i in $(seq 1 30); do sleep 10; if jarvis_ok; then WE_STOPPED=0; notify "Jarvis needed a second start after benchmarks, now up"; return 0; fi; done
  notify "JARVIS IS DOWN after benchmarks. Run: journalctl -u llama-server -n 50"
  return 1
}
on_stop() {
  log "runner told to stop"
  [ -n "$CUR_UNIT" ] && systemctl stop "$CUR_UNIT"
  exit 143
}
trap on_stop TERM INT
trap 'start_jarvis; log "queue runner exiting"' EXIT

for u in glm-copy glm-verify glm-test; do
  if systemctl is-active --quiet "$u"; then log "refusing to start: $u is still running"; exit 1; fi
done

run_job() {  # label profile hours args...
  local label=$1 profile=$2 hours=$3; shift 3
  local numa envs=(-E CUDA_VISIBLE_DEVICES=)
  case "$profile" in
    cpu1)  numa=(--cpunodebind=1 --membind=1) ;;
    cpu)   numa=(--preferred=1) ;;
    cpuil) numa=(--interleave=all) ;;
    cpuilj) numa=(--interleave=all) ;;  # both sockets, allowed beside Jarvis
    gpu)   numa=(--interleave=all); envs=() ;;
    *) log "FAILED $label: unknown profile $profile"; echo "$label" >> "$FAILED"; return ;;
  esac
  local out=$B/results/$label ts; ts=$(date -u +%Y%m%d-%H%M%S)
  mkdir -p "$out"; chown -R simon:simon "$B/results"
  printf '%s\n' "$*" > "$out/$ts.args"
  log "START $label ($profile, max ${hours}h)"
  local t0; t0=$(date +%s)
  CUR_UNIT="bench-$label"
  systemd-run --wait --collect --quiet --unit="bench-$label" \
    -p User=simon -p Group=simon \
    -p MemoryMax="$MEMMAX" -p MemorySwapMax=0 -p OOMScoreAdjust=1000 \
    -p RuntimeMaxSec=$((hours * 3600)) \
    -p StandardOutput=append:"$out/$ts.jsonl" -p StandardError=append:"$out/$ts.log" \
    "${envs[@]}" /usr/bin/numactl "${numa[@]}" "$BIN" -o "$OUTFMT" "$@"
  local rc=$? mins=$(( ($(date +%s) - t0) / 60 ))
  CUR_UNIT=""
  if [ $rc -eq 0 ]; then log "DONE $label in ${mins} min"; echo "$label" >> "$DONE"
  else log "FAILED $label (exit $rc) after ${mins} min, see $out/$ts.log"; echo "$label" >> "$FAILED"; fi
}

log "queue runner started"
while true; do
  [ -e "$STOP" ] && { log "STOP file found, stopping"; break; }
  NEXT_ON=""; NEXT_OFF=""
  while read -r label profile hours rest; do
    [[ -z "$label" || "$label" == \#* ]] && continue
    grep -qx "$label" "$DONE" "$FAILED" && continue
    case "$profile" in
      cpuil|gpu) [ -z "$NEXT_OFF" ] && NEXT_OFF="$label $profile $hours $rest" ;;
      *)         [ -z "$NEXT_ON" ]  && NEXT_ON="$label $profile $hours $rest" ;;
    esac
  done < "$Q"
  OFF_OK=0
  if [ -n "$NEXT_OFF" ] && [ "$NO_OFF" -eq 0 ] && in_window && [ "$(off_minutes)" -lt "$MAX_OFF_MIN" ]; then
    OFF_OK=1
  fi
  if [ "$OFF_OK" -eq 1 ]; then
    stop_jarvis || { notify "could not stop Jarvis, skipping offline jobs tonight"; NO_OFF=1; continue; }
    run_job $NEXT_OFF
  elif [ -n "$NEXT_ON" ]; then
    start_jarvis
    run_job $NEXT_ON
  else
    [ -n "$NEXT_OFF" ] && log "offline jobs left for the next night window: start the runner again then"
    break
  fi
done
start_jarvis
n_done=$(wc -l < "$DONE"); n_fail=$(wc -l < "$FAILED")
notify "Benchmark queue finished: $n_done done, $n_fail failed. Details: ~/bench/queue.log"
