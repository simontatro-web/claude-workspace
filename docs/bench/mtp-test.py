#!/usr/bin/env python3
# MTP speculative-decoding test for Qwen3.8-Flash-Next with the PR #28243 build (llama-server).
# For each config: start llama-server on 127.0.0.1:8083 (socket 1 only, GPUs hidden), run fixed prompts
# at temperature 0, record speed and draft acceptance, check the text is IDENTICAL to MTP off, stop the server.
# Run it as a unit (survives SSH drops), only when no benchmark is running:
#   sudo systemd-run --unit=mtp-test -p User=simon -p Group=simon -p MemoryMax=240G -p MemorySwapMax=0 -p OOMScoreAdjust=1000 /usr/bin/python3 /home/simon/bench/mtp-test.py
# Watch: journalctl -u mtp-test -f     Results: ~/bench/results/fn-mtp/<time>/summary.txt
import json, os, subprocess, sys, time, urllib.request

BIN = "/home/simon/llama.cpp-fnmtp/build/bin/llama-server"
FN = "/home/simon/models/Qwen3.8-Flash-Next-unsloth"
MODEL = FN + "/UD-Q4_K_XL/Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf"
MTP = FN + "/MTP/"
PORT = 8083
CONFIGS = [  # name, draft file (None = MTP off), n-max
    ("off", None, 0),
    ("sharedQ8-n1", "mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf", 1),
    ("sharedQ8-n2", "mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf", 2),
    ("sharedQ8-n3", "mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf", 3),
    ("sharedQ8-n4", "mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf", 4),
    ("sharedQ4-n2", "mtp-Qwen3.8-Flash-Next-shared-Q4_K_M.gguf", 2),
    ("fullQ8-n2", "mtp-Qwen3.8-Flash-Next-Q8_0.gguf", 2),
]
PROMPTS = {
    "reasoning": "A train leaves at 9:40 and travels 150 km at 60 km/h, then stops for 25 minutes, then travels 90 km at 45 km/h. At what time does it arrive? Show your working step by step.",
    "copy": "Rewrite this Python function exactly, changing only the variable name 'total' to 'running_sum' everywhere:\n\ndef add_all(values):\n    total = 0\n    for v in values:\n        if v is None:\n            continue\n        total += v\n    return total\n\ndef mean(values):\n    total = add_all(values)\n    count = len([v for v in values if v is not None])\n    return total / count if count else 0.0\n",
    "prose": "Explain in three short paragraphs how a refrigerator keeps food cold.",
}
MAX_TOKENS = 300

def log(msg):
    print(time.strftime("%H:%M:%SZ", time.gmtime()), msg, flush=True)

def active(unit):
    return subprocess.run(["systemctl", "is-active", "--quiet", unit]).returncode == 0

def post(path, body, timeout=3600):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def healthy():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=5) as r:
            return b"ok" in r.read()
    except Exception:
        return False

for u in ("bench-queue", "glm-test"):
    if active(u):
        sys.exit(f"refusing to start: {u} is running (a benchmark would be distorted)")
if healthy():
    sys.exit(f"refusing to start: something already answers on port {PORT}")

out = os.path.expanduser("~/bench/results/fn-mtp/" + time.strftime("%Y%m%d-%H%M%S", time.gmtime()))
os.makedirs(out, exist_ok=True)
rows, baseline = [], {}
env = dict(os.environ, CUDA_VISIBLE_DEVICES="")
for name, draft, nmax in CONFIGS:
    cmd = ["/usr/bin/numactl", "--cpunodebind=1", "--membind=1", BIN, "-m", MODEL, "-lm", "dio", "-lzm", "off",
           "-ngl", "0", "-t", "18", "-c", "16384", "--parallel", "1", "--jinja",
           "--host", "127.0.0.1", "--port", str(PORT)]
    if draft:
        cmd += ["-md", MTP + draft, "--spec-type", "draft-mtp", "--spec-draft-n-max", str(nmax)]
    log(f"config {name}: starting server")
    lf = open(f"{out}/{name}.server.log", "w")
    proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, env=env)
    t0 = time.time()
    while not healthy():
        if proc.poll() is not None:
            break
        if time.time() - t0 > 1800:
            break
        time.sleep(5)
    if not healthy():
        log(f"config {name}: server did not come up (see {name}.server.log)")
        rows.append((name, "-", "SERVER FAILED", "", "", ""))
        if proc.poll() is None:
            proc.terminate(); proc.wait(timeout=120)
        lf.close()
        continue
    log(f"config {name}: up after {time.time() - t0:.0f} s")
    for pname, ptext in PROMPTS.items():
        body = {"messages": [{"role": "user", "content": ptext}], "temperature": 0, "top_k": 1,
                "seed": 42, "max_tokens": MAX_TOKENS, "cache_prompt": False}
        try:
            r = post("/v1/chat/completions", body)
        except Exception as e:
            rows.append((name, pname, f"REQUEST FAILED: {e}", "", "", "")); continue
        json.dump(r, open(f"{out}/{name}.{pname}.json", "w"), indent=1)
        msg = r["choices"][0]["message"]
        text = (msg.get("reasoning_content") or "") + "\n---\n" + (msg.get("content") or "")
        t = r.get("timings", {})
        acc = f"{t.get('draft_n_accepted', '?')}/{t.get('draft_n', '?')}" if draft else ""
        if name == "off":
            baseline[pname] = text; same = "baseline"
        else:
            same = "IDENTICAL" if baseline.get(pname) == text else "DIFFERENT"
        rows.append((name, pname, f"{t.get('predicted_per_second', 0):.2f}", f"{t.get('prompt_per_second', 0):.1f}", acc, same))
        log(f"  {pname}: tg {rows[-1][2]} t/s, pp {rows[-1][3]} t/s, draft {acc}, {same}")
    proc.terminate(); proc.wait(timeout=120); lf.close()

with open(f"{out}/summary.txt", "w") as f:
    f.write(f"{'config':<13}{'prompt':<11}{'decode t/s':>11}{'prefill t/s':>13}{'draft acc/n':>13}  output vs MTP off\n")
    for r in rows:
        f.write(f"{r[0]:<13}{r[1]:<11}{r[2]:>11}{r[3]:>13}{r[4]:>13}  {r[5]}\n")
print(open(f"{out}/summary.txt").read(), flush=True)
log(f"done. Results in {out}")
