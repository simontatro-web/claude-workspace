#!/usr/bin/env python3
# Tests Flash-Next spread over BOTH sockets (numactl --interleave=all) while Jarvis keeps running,
# and measures Jarvis's own answer speed before, during and after. Stops the benchmark by itself
# if Jarvis slows below LIMIT of its normal speed on two probes in a row.
# Run as root in a unit, only when no other benchmark is running:
#   sudo systemd-run --unit=il-beside /usr/bin/python3 /home/simon/bench/il-beside.py
# Watch: journalctl -u il-beside -f     Results: ~/bench/results/fn-il-beside/<time>/
import json, os, pwd, statistics, subprocess, sys, time, urllib.request

LIMIT = 0.75          # stop if Jarvis drops below 75% of its baseline speed twice in a row
PROBE_EVERY = 60      # seconds between Jarvis probes during the benchmark
BENCH = "/home/simon/llama.cpp/build/bin/llama-bench"
MODEL = "/home/simon/models/Qwen3.8-Flash-Next-unsloth/UD-Q4_K_XL/Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf"
ARGS = ["-m", MODEL, "-lm", "dio", "-lzm", "off", "-ngl", "0", "-t", "36,32", "-p", "512", "-n", "128", "-r", "3"]
UNIT = "bench-fn-il-beside"
PROBE = {"messages": [{"role": "user", "content": "List the planets of the solar system in order from the Sun, with one short fact about each."}],
         "temperature": 0, "max_tokens": 200, "cache_prompt": False}

def log(msg):
    print(time.strftime("%H:%M:%SZ", time.gmtime()), msg, flush=True)

def active(unit):
    return subprocess.run(["systemctl", "is-active", "--quiet", unit]).returncode == 0

def jarvis_tps():
    req = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions", data=json.dumps(PROBE).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return float(json.loads(r.read())["timings"]["predicted_per_second"])
    except Exception as e:
        log(f"Jarvis probe failed: {e}")
        return None

for u in ("bench-queue", "mtp-test", "glm-test", UNIT):
    if active(u):
        sys.exit(f"refusing to start: {u} is running")
if not active("llama-server"):
    sys.exit("refusing to start: Jarvis (llama-server) is not running, nothing to measure beside")

simon = pwd.getpwnam("simon")
out = "/home/simon/bench/results/fn-il-beside/" + time.strftime("%Y%m%d-%H%M%S", time.gmtime())
os.makedirs(out, exist_ok=True)
rec = {"before": [], "during": [], "after": [], "stopped_early": False}

log("Jarvis baseline, 3 probes")
for _ in range(3):
    v = jarvis_tps(); log(f"  Jarvis {v} t/s"); rec["before"].append(v)
base = statistics.median([v for v in rec["before"] if v] or [0])
if not base:
    sys.exit("Jarvis did not answer the baseline probes; not starting")

subprocess.run(["systemctl", "reset-failed", UNIT], stderr=subprocess.DEVNULL)
cmd = ["systemd-run", "--unit=" + UNIT, "--collect", "-p", "User=simon", "-p", "Group=simon",
       "-p", "MemoryMax=240G", "-p", "MemorySwapMax=0", "-p", "OOMScoreAdjust=1000", "-p", "RuntimeMaxSec=3600",
       "-p", f"StandardOutput=append:{out}/bench.jsonl", "-p", f"StandardError=append:{out}/bench.log",
       "-E", "CUDA_VISIBLE_DEVICES=", "/usr/bin/numactl", "--interleave=all", BENCH, "-o", "jsonl"] + ARGS
subprocess.run(cmd, check=True)
log(f"benchmark started as {UNIT}; Jarvis baseline {base:.2f} t/s, stop below {LIMIT * base:.2f}")

low = 0
time.sleep(30)
while active(UNIT):
    v = jarvis_tps(); rec["during"].append(v)
    log(f"  during: Jarvis {v} t/s")
    low = low + 1 if (v is None or v < LIMIT * base) else 0
    if low >= 2:
        log("Jarvis slowed too much twice in a row: stopping the benchmark")
        subprocess.run(["systemctl", "stop", UNIT]); rec["stopped_early"] = True
        break
    for _ in range(PROBE_EVERY):
        if not active(UNIT):
            break
        time.sleep(1)

time.sleep(10)
log("Jarvis after, 3 probes")
for _ in range(3):
    v = jarvis_tps(); log(f"  Jarvis {v} t/s"); rec["after"].append(v)

def med(xs):
    xs = [x for x in xs if x]; return f"{statistics.median(xs):.2f}" if xs else "n/a"
lines = [f"Jarvis t/s median: before {med(rec['before'])}, during {med(rec['during'])} (min {min([x for x in rec['during'] if x] or [0]):.2f}), after {med(rec['after'])}",
         f"stopped early: {rec['stopped_early']}", "Flash-Next (interleaved, beside Jarvis):"]
for line in open(f"{out}/bench.jsonl"):
    try:
        d = json.loads(line)
        lines.append(f"  threads {d['n_threads']}  pp {d['n_prompt']}  tg {d['n_gen']}  {d['avg_ts']:.2f} t/s")
    except Exception:
        pass
json.dump(rec, open(f"{out}/jarvis-probes.json", "w"), indent=1)
open(f"{out}/summary.txt", "w").write("\n".join(lines) + "\n")
for root, dirs, files in os.walk(os.path.dirname(out)):
    for n in dirs + files:
        os.chown(os.path.join(root, n), simon.pw_uid, simon.pw_gid)
os.chown(os.path.dirname(out), simon.pw_uid, simon.pw_gid)
print("\n".join(lines), flush=True)
log(f"done. Results in {out}")
