# SIMON STEP: paste this whole block into your SSH terminal on jarvis-1 (as simon). It only writes two files under ~/speed/scripts.
mkdir -p ~/speed/scripts ~/speed/results ~/speed/models
cat > ~/speed/scripts/j27_logstats.py <<'J27_LOGSTATS_END'
#!/usr/bin/env python3
# Summarise llama-server speed from its journal (read-only). Prints under ~2,500 characters.
# Usage: journalctl -u llama-server --since "-48h" -o cat --no-pager | python3 ~/speed/scripts/j27_logstats.py
import re, sys, statistics

P_PROMPT = re.compile(r"task (\d+) \| prompt eval time = +([\d.]+) ms / +(\d+) tokens .*?([\d.]+) tokens per second")
P_EVAL = re.compile(r"task (\d+) \| +eval time = +([\d.]+) ms / +(\d+) tokens .*?([\d.]+) tokens per second")
P_DRAFT = re.compile(r"task (\d+) \| draft acceptance = ([\d.]+) \( *(\d+) accepted / +(\d+) generated\), mean len = +([\d.]+)")
P_STOP = re.compile(r"task (\d+) \| stop processing: n_tokens = (\d+), truncated = (\d)")

tasks = {}
restarts = 0
for line in sys.stdin:
    if "server is listening" in line:
        restarts += 1
    for pat, key in ((P_PROMPT, "p"), (P_EVAL, "e"), (P_DRAFT, "d"), (P_STOP, "s")):
        m = pat.search(line)
        if m:
            tasks.setdefault((restarts, m.group(1)), {})[key] = m.groups()[1:]
            break

def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))] if xs else 0.0

def fmt(xs):
    if not xs:
        return "n=0"
    return "n=%d p10 %.1f | p50 %.1f | p90 %.1f" % (len(xs), pct(xs, .1), pct(xs, .5), pct(xs, .9))

gen, gen_w, prompt_big, ttft, rates, lens, by_len, by_depth = [], [0.0, 0.0], [], [], [], [], {}, {}
max_ctx, trunc, big_reproc = 0, 0, 0
for t in tasks.values():
    if "e" in t:
        ms, n, tps = float(t["e"][0]), int(t["e"][1]), float(t["e"][2])
        if n >= 32:
            gen.append(tps)
            gen_w[0] += n
            gen_w[1] += ms
            if "d" in t:
                ml = float(t["d"][3])
                b = "<2" if ml < 2 else "2-3" if ml < 3 else "3-4" if ml < 4 else ">=4"
                by_len.setdefault(b, []).append(tps)
            if "s" in t:
                d = int(t["s"][0])
                b = "0-8K" if d < 8192 else "8-16K" if d < 16384 else "16-24K" if d < 24576 else ">=24K"
                by_depth.setdefault(b, []).append(tps)
    if "p" in t:
        ms, n, tps = float(t["p"][0]), int(t["p"][1]), float(t["p"][2])
        ttft.append(ms)
        if n >= 1000:
            prompt_big.append(tps)
        if n >= 8000:
            big_reproc += 1
    if "d" in t:
        rates.append(float(t["d"][0]))
        lens.append(float(t["d"][3]))
    if "s" in t:
        max_ctx = max(max_ctx, int(t["s"][0]))
        trunc += int(t["s"][1])

print("tasks parsed: %d | server starts seen: %d" % (len(tasks), restarts))
print("decode t/s (tasks with >=32 generated tokens): " + fmt(gen))
if gen_w[1] > 0:
    print("  token-weighted decode t/s: %.1f over %d tokens" % (gen_w[0] / gen_w[1] * 1000.0, int(gen_w[0])))
for b in ("<2", "2-3", "3-4", ">=4"):
    if b in by_len:
        print("  mean draft len %-4s: %s" % (b, fmt(by_len[b])))
for b in ("0-8K", "8-16K", "16-24K", ">=24K"):
    if b in by_depth:
        print("  context %-6s: %s" % (b, fmt(by_depth[b])))
if rates:
    print("draft acceptance: mean rate %.3f, mean len %.2f (n=%d)" % (statistics.mean(rates), statistics.mean(lens), len(rates)))
print("prefill t/s (prompts with >=1000 new tokens): " + fmt(prompt_big))
print("prompt eval ms per request (time-to-first-token proxy): " + fmt(ttft))
print("requests that re-processed >=8000 prompt tokens: %d" % big_reproc)
print("max context at release: %d tokens | truncated=1 events: %d" % (max_ctx, trunc))
J27_LOGSTATS_END
cat > ~/speed/scripts/t27_window.py <<'T27_WINDOW_END'
#!/usr/bin/env python3
# SIMON ONLY. Downtime-window speed test for Jarvis's 27B (Qwen3.8-27B Q4_K_M, 2x V100).
# It STOPS llama-server (Jarvis), runs each named config as a test llama-server on 127.0.0.1:8081
# (transient unit t27-srv), and ALWAYS starts llama-server again at the end (also on errors/SIGTERM).
# Per config: decode/prefill speed, speed at 16K depth, VRAM peak, greedy output vs the non-speculative
# reference (identical, or first difference at a near-tie measured with the reference's top-2 logprobs),
# and a 12-item quality set. Stored references are reused unless --fresh-ref.
# Start (as root):  sudo systemd-run --unit=t27-window --collect -p RuntimeMaxSec=7800 \
#   /usr/bin/python3 /home/simon/speed/scripts/t27_window.py ctl graphs pmin03
# Flag override: NAME@-flag=value[@-flag=value], e.g. new-tp@--spec-draft-p-min=0.3  (a value is replaced or appended)
# Watch: journalctl -u t27-window -n 40 --no-pager   Result: ~/speed/results/t27/<time>/summary.txt
import glob, json, os, random, re, signal, subprocess, sys, threading, time, urllib.request

H = os.environ.get("T27_HOME", "/home/simon")  # override only for offline testing
OUTROOT = H + "/speed/results/t27"
REFDIR = OUTROOT + "/refs"
BIN = {"prod": H + "/llama.cpp/build/bin/llama-server", "new": H + "/llama.cpp-tp/build/bin/llama-server",
       "fork": H + "/sm70-attn/build/bin/llama-server"}
MODEL = (sorted(glob.glob(H + "/.cache/huggingface/hub/models--ggml-org--Qwen3.8-27B-GGUF/snapshots/*/Qwen3.8-27B-Q4_K_M.gguf")) or [""])[0]
MTP, DFLASH = H + "/models/mtp-Qwen3.8-27B-Q4_0.gguf", H + "/speed/models/dflash2-27b.gguf"
PORT, UNIT, VRAM_LIMIT = 8081, "t27-srv", 15300
BUSY = re.compile(r"^(bench-.*|mtp-test|il-beside|glm-test.*|fn-test.*|t27-srv|big-verify|build-.*|dl-.*)\.service$")

BASE = ["-m", MODEL, "-ngl", "99", "-sm", "layer", "-ts", "28,36", "-ctk", "f16", "-ctv", "f16", "-c", "24576",
        "--jinja", "--chat-template-kwargs", '{"reasoning_effort":"xhigh"}', "--no-mmproj",
        "--no-reasoning-preserve", "--parallel", "2", "--kv-unified", "--host", "127.0.0.1", "--port", str(PORT)]
MTPA = ["--spec-type", "draft-mtp", "-md", MTP, "--spec-draft-n-max", "5", "--spec-draft-p-min", "0.4",
        "-devd", "CUDA0", "-ngld", "99"]
DFA = ["--spec-type", "draft-dflash", "-md", DFLASH, "--spec-draft-n-max", "5", "-devd", "CUDA0", "-ngld", "99"]

def setv(args, flag, val):  # replace the value after flag, or append flag+value
    a = list(args)
    if flag in a:
        a[a.index(flag) + 1] = val
    else:
        a += [flag, val]
    return a

def tp(args):  # layer split -> tensor parallel (needs flash attention, no auto-fit)
    a = setv(args, "-sm", "tensor")
    i = a.index("-ts")
    return a[:i] + a[i + 2:] + ["-fa", "on", "-fit", "off"]

C = {}
def cfg(name, fam, args, drop=(), note=""):
    C[name] = {"fam": fam, "args": args, "drop": list(drop), "note": note}
cfg("ref", "prod", BASE, note="production flags, speculation off (reference)")
cfg("ctl", "prod", BASE + MTPA, note="exact production config (control)")
cfg("graphs", "prod", BASE + MTPA, drop=["GGML_CUDA_DISABLE_GRAPHS"], note="CUDA graphs allowed")
for v in ("0", "0.3", "0.5"):
    cfg("pmin" + v.replace(".", ""), "prod", setv(BASE + MTPA, "--spec-draft-p-min", v), note="p-min " + v)
for v in ("3", "4", "6"):
    cfg("nmax" + v, "prod", setv(BASE + MTPA, "--spec-draft-n-max", v), note="n-max " + v)
cfg("bsamp", "prod", BASE + MTPA + ["-bs"], note="backend sampling (experimental)")
for v in ("5", "7"):
    cfg("dflash" + v, "prod", setv(BASE + DFA, "--spec-draft-n-max", v), note="DFlash2 draft n-max " + v)
cfg("new-ref", "new", BASE, note="new build, speculation off (reference)")
cfg("new-ctl", "new", BASE + MTPA, note="new build, production flags (FA auto)")
cfg("new-faoff", "new", BASE + MTPA + ["-fa", "off"], note="new build, FA forced off")
cfg("new-ub1024", "new", BASE + MTPA + ["-ub", "1024"], note="new build, ubatch 1024")
cfg("new-c64k", "new", setv(BASE + MTPA, "-c", "65536"), note="new build, 64K context")
cfg("new-tp-ref", "new", tp(BASE), note="tensor parallel, speculation off")
cfg("new-tp", "new", tp(BASE) + MTPA, note="tensor parallel + MTP")
for v in ("3", "4"):
    cfg("new-tp-n" + v, "new", setv(tp(BASE) + MTPA, "--spec-draft-n-max", v), note="TP + MTP n-max " + v)
cfg("new-tp-dflash", "new", tp(BASE) + DFA, note="tensor parallel + DFlash2")
cfg("new-tp-c64k", "new", setv(tp(BASE) + MTPA, "-c", "65536"), note="TP + MTP, 64K context")
cfg("new-tp-ts", "new", tp(BASE) + MTPA + ["-ts", "46,54"], note="TP + MTP, split 46/54 (draft sits on CUDA0)")
cfg("fork-ctl", "fork", BASE + MTPA + ["-fa", "on"], note="sm70-attn fork, FA on")
cfg("fork-faoff", "fork", BASE + MTPA + ["-fa", "off"], note="sm70-attn fork, FA off")

SPEED = [("reasoning", "A train leaves at 9:40 and travels 150 km at 60 km/h, then stops for 25 minutes, then travels 90 km at 45 km/h. At what time does it arrive? Show your working step by step.", "xhigh", 512),
         ("copy", "Rewrite this Python function exactly, changing only the variable name 'total' to 'running_sum' everywhere:\n\ndef add_all(values):\n    total = 0\n    for v in values:\n        if v is None:\n            continue\n        total += v\n    return total\n\ndef mean(values):\n    total = add_all(values)\n    count = len([v for v in values if v is not None])\n    return total / count if count else 0.0\n", "low", 512),
         ("prose", "Explain in three short paragraphs how a refrigerator keeps food cold.", "low", 512),
         ("long", "Count from 1 to 400. Write only the numbers, separated by single spaces.", "low", 1500)]
QUAL = [("What is 17 multiplied by 23? Reply with only the number.", r"\b391\b"),
        ("What is the capital city of Australia? Reply with one word.", r"(?i)\bcanberra\b"),
        ("Sort these numbers from smallest to largest, comma-separated, nothing else: 42, 7, 19, 3, 88", r"3,\s*7,\s*19,\s*42,\s*88"),
        ("How many vowels (a, e, i, o, u) are in the phrase 'Programming Language'? Reply with only the number.", r"\b7\b"),
        ("A train covers 150 km at a constant 60 km/h. How many minutes does the trip take? Reply with only the number.", r"\b150\b"),
        ("Spell the word 'necessary' backwards. Reply with only the reversed word.", r"(?i)\byrassecen\b"),
        ("What is the chemical symbol for sodium? Reply with only the symbol.", r"\bNa\b"),
        ("What is 2 to the power of 12? Reply with only the number.", r"\b4096\b"),
        ("A $40 shirt is discounted by 25%. What is the sale price in dollars? Reply with only the number.", r"\b30(\.00?)?\b"),
        ("Which number is larger, 0.9 or 0.11? Reply with only that number.", r"\b0\.9\b(?!\d)"),
        ("Write a Python function is_even(n) that returns True for even integers. Reply with only the code.", r"def is_even\(n\)[\s\S]*%\s*2"),
        ("If today is Monday, what day of the week is it 10 days from now? Reply with one word.", r"(?i)\bthursday\b")]

def doc(n_lines, seed):  # deterministic filler document with one needle
    r = random.Random(seed)
    words = "copper wire crates audit Denver ledger harbor valve signal orchard tunnel beacon quartz meadow".split()
    lines = ["Record %04d: the %s depot shipped %d %s units on day %d; audit code %s%d%s." % (
        i, r.choice(words), r.randint(2, 99), r.choice(words), r.randint(1, 28), r.choice("KQXZ"), r.randint(1, 9),
        r.choice("ABCD")) for i in range(1, n_lines + 1)]
    return "\n".join(lines) + "\n\nWhich record number mentions audit code %s? Reply with only the number." % lines[6].split()[-1].rstrip(".")

LONGDOCS = [("pp6k", doc(200, 7), "low", 16), ("d16k", doc(520, 11), "low", 256)]
STOP = {"flag": False}

def log(msg):
    print(time.strftime("%H:%M:%SZ", time.gmtime()), msg, flush=True)

def sh(cmd, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

def active(unit):
    return sh(["systemctl", "is-active", "--quiet", unit]).returncode == 0

def vram():
    r = sh(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], 30)
    return [int(x) for x in r.stdout.split()] if r.returncode == 0 else []

def wait_vram_free(limit=1000, secs=180):
    t0 = time.time()
    while time.time() - t0 < secs:
        v = vram()
        if v and max(v) < limit:
            return True
        time.sleep(3)
    return False

def http(path, body=None, port=PORT, timeout=600):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def healthy(port=PORT):
    try:
        return http("/health", port=port, timeout=5).get("status") == "ok"
    except Exception:
        return False

class VramPeak(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.peak, self.run_flag = [], True
    def run(self):
        while self.run_flag:
            v = vram()
            if v:
                self.peak = [max(a, b) for a, b in zip(self.peak, v)] if len(self.peak) == len(v) else v
            time.sleep(2)

def prod_env():
    s = sh(["systemctl", "show", "-p", "Environment", "--value", "llama-server"]).stdout.strip()
    return dict(x.split("=", 1) for x in s.split() if "=" in x)

def start_srv(name, c, outdir, env):
    sh(["systemctl", "reset-failed", UNIT])
    e = [x for k, v in env.items() if k not in c["drop"] for x in ("-E", "%s=%s" % (k, v))]
    cmd = ["systemd-run", "--unit=" + UNIT, "--collect", "-p", "User=simon", "-p", "Group=simon", "-p", "MemoryMax=48G",
           "-p", "MemorySwapMax=0", "-p", "OOMScoreAdjust=1000", "-p", "StandardOutput=append:%s/%s.log" % (outdir, name),
           "-p", "StandardError=append:%s/%s.log" % (outdir, name)] + e + [
           "/usr/bin/numactl", "--cpunodebind=0", "--membind=0", BIN[c["fam"]]] + c["args"]
    if sh(cmd).returncode != 0:
        return False
    t0 = time.time()
    while time.time() - t0 < 420 and not STOP["flag"]:
        if healthy():
            log("  %s up after %.0f s" % (name, time.time() - t0))
            return True
        if not active(UNIT):
            break
        time.sleep(3)
    return False

def stop_srv():
    if active(UNIT):
        sh(["systemctl", "stop", UNIT])
    wait_vram_free()

def complete(prompt, n, probs=False):
    b = {"prompt": prompt, "n_predict": n, "temperature": 0, "top_k": 1, "seed": 42, "cache_prompt": False}
    if probs:
        b["n_probs"] = 2
    r = http("/completion", b)
    t = r.get("timings", {})
    out = {"text": r.get("content", ""), "tg": t.get("predicted_per_second", 0.0), "pp": t.get("prompt_per_second", 0.0),
           "np": t.get("prompt_n", 0), "ng": t.get("predicted_n", 0), "dn": t.get("draft_n", 0), "da": t.get("draft_n_accepted", 0)}
    if probs:
        out["toks"] = [[p.get("bytes", []), [[q.get("bytes", []), q.get("logprob", 0.0)] for q in p.get("top_logprobs", [])[:2]]]
                       for p in r.get("completion_probabilities", [])]
    return out

def templ(text, effort):
    return http("/apply-template", {"messages": [{"role": "user", "content": text}],
                                    "chat_template_kwargs": {"reasoning_effort": effort}})["prompt"]

def compare(ref, text):  # IDENTICAL / NEAR-TIE gap / DIVERGED gap, using the reference's top-2 logprobs
    a, b = ref["text"].encode(), text.encode()
    d = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), None)
    if d is None:
        if len(a) == len(b):
            return ("IDENTICAL", 0.0)
        d = min(len(a), len(b))  # one output stopped earlier: judge the token where they part
    pos = 0
    for tb, top in ref.get("toks", []):
        if pos + len(tb) > d:
            gap = top[0][1] - top[1][1] if len(top) >= 2 else 99.0
            return ("NEAR-TIE" if gap <= 0.10 else "DIVERGED", round(gap, 3))
        pos += len(tb)
    return ("PREFIX", 99.0)

def run_tests(prompts, ref_mode):
    res = {"speed": {}, "long": {}, "qual": []}
    for key, text, effort, n in SPEED + LONGDOCS:
        if STOP["flag"]:
            break
        r = complete(prompts[key], n)
        if ref_mode:
            r2 = complete(prompts[key], n, probs=True)
            r["toks"], r["rerun_same"] = r2["toks"], r2["text"] == r["text"]
        (res["long"] if key in ("pp6k", "d16k") else res["speed"])[key] = r
        log("  %-9s tg %6.2f  pp %7.1f  prompt %5d  gen %4d  draft %d/%d" % (key, r["tg"], r["pp"], r["np"], r["ng"], r["da"], r["dn"]))
    for i, (q, rx) in enumerate(QUAL):
        if STOP["flag"]:
            break
        r = complete(prompts["q%d" % i], 1024, probs=ref_mode)
        r["ok"] = "</think>" in r["text"] and bool(re.search(rx, r["text"].split("</think>")[-1]))
        res["qual"].append(r)
    return res

def vs(ref, res):
    if not ref:
        return {"IDENTICAL": 0, "PREFIX": 0, "NEAR-TIE": 0, "DIVERGED": 0}, 0.0
    cmp = [compare(ref["speed"][k], r["text"]) for k, r in res["speed"].items() if k in ref["speed"]]
    cmp += [compare(ref["qual"][i], q["text"]) for i, q in enumerate(res["qual"]) if i < len(ref["qual"])]
    kinds = {k: sum(1 for s, _ in cmp if s == k) for k in ("IDENTICAL", "PREFIX", "NEAR-TIE", "DIVERGED")}
    return kinds, max((g for s, g in cmp if s != "IDENTICAL"), default=0.0)

def summarise(name, c, res, ref, famref, peak):
    sp = res["speed"]
    dec = [sp[k]["tg"] for k in ("reasoning", "copy", "prose") if k in sp]
    kinds, worst = vs(ref, res)
    fkinds, fworst = vs(famref, res)
    dn = sum(sp[k]["dn"] for k in sp)
    return {"name": name, "note": c["note"], "dec": [round(x, 2) for x in dec], "dec_mean": round(sum(dec) / len(dec), 2) if dec else 0,
            "long": round(sp.get("long", {}).get("tg", 0), 2), "pp6k": round(res["long"].get("pp6k", {}).get("pp", 0), 1),
            "d16k_pp": round(res["long"].get("d16k", {}).get("pp", 0), 1), "d16k_tg": round(res["long"].get("d16k", {}).get("tg", 0), 2),
            "acc": round(sum(sp[k]["da"] for k in sp) / dn, 3) if dn else None, "vram": peak,
            "vs_ref": kinds, "worst_gap": round(worst, 3), "vs_fam": fkinds, "fam_gap": round(fworst, 3),
            "qual": "%d/%d" % (sum(q["ok"] for q in res["qual"]), len(res["qual"]))}

def fmt_row(s):
    v = "/".join(str(x) for x in s["vram"]) if s["vram"] else "?"
    k = s["vs_ref"]
    f = s["vs_fam"]
    fam = " | vs own-build ref: %dI %dP %dT %dD gap %.3f" % (f["IDENTICAL"], f["PREFIX"], f["NEAR-TIE"], f["DIVERGED"], s["fam_gap"]) if sum(f.values()) else ""
    ref = "vs prod ref: %dI %dP %dT %dD gap %.3f" % (k["IDENTICAL"], k["PREFIX"], k["NEAR-TIE"], k["DIVERGED"], s["worst_gap"]) if sum(k.values()) else "vs prod ref: n/a"
    rr = " | reference re-run identical %s" % s["rerun_identical"] if "rerun_identical" in s else ""
    return ("%-13s dec %s mean %.2f | long %.2f | pp6k %.0f | 16K pp %.0f tg %.2f | acc %s | VRAM %s | %s%s | qual %s%s"
            % (s["name"], "/".join("%.1f" % x for x in s["dec"]), s["dec_mean"], s["long"], s["pp6k"], s["d16k_pp"], s["d16k_tg"],
               s["acc"], v, ref, fam, s["qual"], rr))

def restore_prod():
    stop_srv()
    for attempt in (1, 2):
        sh(["systemctl", "start" if attempt == 1 else "restart", "llama-server"])
        t0 = time.time()
        while time.time() - t0 < 300:
            if healthy(8080):
                try:
                    r = http("/v1/chat/completions", {"messages": [{"role": "user", "content": "Say OK."}], "max_tokens": 200,
                                                      "temperature": 0, "chat_template_kwargs": {"reasoning_effort": "low"}},
                             port=8080, timeout=300)
                    return "yes, healthy after %.0f s (attempt %d), probe answered: %r" % (
                        time.time() - t0, attempt, (r["choices"][0]["message"].get("content") or "")[:40])
                except Exception as e:
                    return "health ok but probe failed: %s" % e
            time.sleep(5)
    return "NO - llama-server not healthy after two tries: run  journalctl -u llama-server -n 50"

def derive(name):  # "base@-flag=value@-flag2=value2": a known config with some flag values replaced
    parts = name.split("@")
    if parts[0] not in C or any("=" not in x for x in parts[1:]):
        return False
    args = C[parts[0]]["args"]
    for x in parts[1:]:
        flag, val = x.split("=", 1)
        args = setv(args, flag, val)
    C[name] = dict(C[parts[0]], args=args, note=C[parts[0]]["note"] + " + " + " ".join(parts[1:]))
    return True

def main():
    names = [a for a in sys.argv[1:] if not a.startswith("--") or "@" in a]
    names = [n for n in names if n in C or derive(n) or n]
    fresh = "--fresh-ref" in sys.argv
    max_min = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--max-min=")), "100"))
    bad = [n for n in names if n not in C]
    if os.geteuid() != 0 or bad or not MODEL:
        sys.exit("need root, known config names (%s), and the model file; unknown: %s" % (" ".join(C), bad))
    busy = [u for u in sh(["systemctl", "list-units", "--type=service", "--state=active", "--no-legend", "--plain"]).stdout.split()
            if BUSY.match(u)]
    if busy or not active("llama-server") or healthy():
        sys.exit("refusing: busy units %s / llama-server active=%s / port %d in use=%s" % (busy, active("llama-server"), PORT, healthy()))
    out = time.strftime(OUTROOT + "/%Y%m%d-%H%M%S", time.gmtime())
    os.makedirs(REFDIR, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    env = prod_env()
    order = []
    for n in names:
        fam_ref = "ref" if C[n]["fam"] == "prod" else ("new-ref" if C[n]["fam"] == "new" else None)
        for x in (["ref", "ctl"] if C[n]["fam"] == "prod" else ["ref", "ctl", fam_ref]):
            if x and x not in order and x != n:
                order.append(x)
        if n not in order:
            order.append(n)
    refs, rows, allres, t_start = {}, [], {}, time.time()
    log("order: %s | production env: %s" % (" ".join(order), env))
    summary = out + "/summary.txt"
    try:
        log("stopping llama-server (Jarvis is offline from now until the end of this run)")
        sh(["systemctl", "stop", "llama-server"])
        if not wait_vram_free():
            raise RuntimeError("GPUs did not free after stopping llama-server: %s" % vram())
        for name in order:
            c = C[name]
            if STOP["flag"] or time.time() - t_start > (max_min - 12) * 60:
                rows.append({"name": name, "skipped": "time or stop"})
                continue
            need = [f for f in (BIN[c["fam"]], c["args"][c["args"].index("-m") + 1], MTP if MTP in c["args"] else None,
                                DFLASH if DFLASH in c["args"] else None) if f]
            missing = [f for f in need if not os.path.exists(f)]
            libm = int(os.path.getmtime(BIN[c["fam"]])) if os.path.exists(BIN[c["fam"]]) else 0
            refpath = "%s/%s-%d.json" % (REFDIR, c["fam"], libm)
            is_ref = name in ("ref", "new-ref")
            if missing or (is_ref and not fresh and os.path.exists(refpath)):
                if missing:
                    rows.append({"name": name, "skipped": "missing " + " ".join(missing)})
                else:
                    refs[c["fam"]] = json.load(open(refpath))
                    rows.append({"name": name, "skipped": "reused stored reference " + os.path.basename(refpath)})
                    log("%s: reusing stored reference %s" % (name, refpath))
                continue
            log("config %s: %s" % (name, c["note"]))
            if not start_srv(name, c, out, env):
                rows.append({"name": name, "error": "server did not start (see %s.log)" % name})
                stop_srv()
                continue
            mon = VramPeak()
            mon.start()
            try:
                prompts = (refs.get("prod") or refs.get(c["fam"]) or {}).get("prompts")
                if not prompts:
                    prompts = {k: templ(t, e) for k, t, e, _ in SPEED + LONGDOCS}
                    prompts.update({"q%d" % i: templ(q, "low") for i, (q, _) in enumerate(QUAL)})
                res = run_tests(prompts, is_ref)
                res["prompts"] = prompts
                if is_ref:
                    refs[c["fam"]] = res
                    json.dump(res, open(refpath, "w"))
                    same = [k for k, r in res["speed"].items() if r.get("rerun_same")]
                    log("  reference re-run identical on %d/%d prompts" % (len(same), len(res["speed"])))
                mon.run_flag = False
                time.sleep(2)
                famref = refs.get(c["fam"]) if c["fam"] != "prod" and not is_ref else None
                s = summarise(name, c, res, None if name == "ref" else refs.get("prod"), famref, mon.peak)
                if is_ref:
                    s["rerun_identical"] = "%d/%d" % (sum(1 for r in res["speed"].values() if r.get("rerun_same")), len(res["speed"]))
                rows.append(s)
                allres[name] = {k: v for k, v in res.items() if k != "prompts"}
                log("  " + fmt_row(s))
            except Exception as e:
                rows.append({"name": name, "error": "tests failed: %s" % e})
                log("  tests failed: %s" % e)
            finally:
                mon.run_flag = False
                stop_srv()
            json.dump({"rows": rows, "results": allres}, open(out + "/results.json", "w"))
    finally:
        restored = restore_prod()
        log("Jarvis restored: " + restored)
        with open(summary, "w") as f:
            f.write("t27 window %s UTC | limit VRAM %d MiB per GPU | near-tie = top-2 gap <= 0.10 nats\n" % (os.path.basename(out), VRAM_LIMIT))
            for s in rows:
                f.write((fmt_row(s) if "dec" in s else "%-13s %s" % (s["name"], s.get("skipped") or s.get("error"))) + "\n")
            f.write("Jarvis restored: %s\n" % restored)
        subprocess.run(["chown", "-R", "simon:simon", OUTROOT])
        print(open(summary).read(), flush=True)

def on_term(signum, frame):
    STOP["flag"] = True
    log("stop requested: stopping the test server, then restoring Jarvis")
    subprocess.Popen(["systemctl", "stop", "--no-block", UNIT])

signal.signal(signal.SIGTERM, on_term)
signal.signal(signal.SIGINT, on_term)
if __name__ == "__main__":
    main()
T27_WINDOW_END
for f in ~/speed/scripts/j27_logstats.py ~/speed/scripts/t27_window.py; do echo "$(basename $f): $(wc -l < $f) lines, $(wc -c < $f) bytes, $(sha256sum $f | cut -c1-16)"; done
# expected: j27_logstats.py: 77 lines, 3464 bytes, fb7817288dbaffa2
# expected: t27_window.py: 390 lines, 22533 bytes, 05d965589667b06d
