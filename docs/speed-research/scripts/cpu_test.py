#!/usr/bin/env python3
# CPU big-model tester that runs BESIDE Jarvis. It never stops or changes llama-server (Jarvis).
# Starts a test llama-server as a child process (CPU only, GPUs hidden) on 127.0.0.1:8082 with the given
# binary, model, NUMA policy and flags, then measures: load time, RAM per NUMA node, decode and prefill
# speed, draft acceptance, greedy output vs a stored reference (IDENTICAL, or first difference at a
# NEAR-TIE = reference top-2 logprob gap <= 0.10 nats), prompt-cache reuse, slot save/restore, 2-slot
# throughput and a 12-item quality set. Probes Jarvis (port 8080) before/during/after; stops itself if Jarvis answers
# below 75% of its normal speed on two probes in a row. Mainline builds need -lv 4 in the server flags
# for the cache test to count checkpoint log lines (token counts work without it).
# Run as a unit, only when no other benchmark is active, e.g.:
#   sudo systemd-run --unit=cpu-test --collect -p User=simon -p Group=simon -p MemoryMax=160G -p MemorySwapMax=0
#     -p OOMScoreAdjust=1000 -p RuntimeMaxSec=10800 /usr/bin/python3 /home/simon/speed/scripts/cpu_test.py
#     fn-base --bin stock --model fn --numa il --make-ref fn-stock --tests speed,prefill -- -lm dio -lzm off -t 18 -tb 36
# --check prints the resolved command and the precondition results, then exits without loading anything.
# Watch: journalctl -u cpu-test -n 30 --no-pager     Result: ~/speed/results/cpu/<label>/<UTC time>/summary.txt
import argparse, glob, json, os, random, re, signal, socket, statistics, subprocess, sys, threading, time, urllib.request

H = os.environ.get("CPU_TEST_HOME", "/home/simon")          # overrides only for offline testing
JPORT = int(os.environ.get("CPU_TEST_JPORT", "8080"))
MARGIN = float(os.environ.get("CPU_TEST_MARGIN_GIB", "16"))
OUTROOT, PORT = H + "/speed/results/cpu", 8082
REFDIR = OUTROOT + "/refs"
BINS = {"stock": H + "/llama.cpp/build/bin/llama-server", "fnmtp": H + "/llama.cpp-fnmtp/build/bin/llama-server",
        "new": H + "/llama.cpp-tp/build/bin/llama-server", "ik": H + "/ik_llama.cpp/build/bin/llama-server",
        "ikmirror": H + "/ik-mirror/build/bin/llama-server"}
MODELS = {"fn": H + "/models/Qwen3.8-Flash-Next-unsloth/UD-Q4_K_XL/Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf",
          "glm": H + "/models/GLM-5.3/UD-Q4_K_XL/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf"}
NUMA = {"s1": ["/usr/bin/numactl", "--cpunodebind=1", "--membind=1"], "il": ["/usr/bin/numactl", "--interleave=all"],
        "p1": ["/usr/bin/numactl", "--preferred=1"], "none": []}
BUSY = re.compile(r"^(bench-.*|mtp-test|il-beside|glm-test.*|fn-test.*|t27-.*|big-verify|build-.*|dl-.*|kld-.*)\.service$")
LIMIT, PROBE_EVERY = 0.75, 90

SPEED = [("reasoning", "A train leaves at 9:40 and travels 150 km at 60 km/h, then stops for 25 minutes, then travels 90 km at 45 km/h. At what time does it arrive? Show your working step by step.", "high"),
         ("copy", "Rewrite this Python function exactly, changing only the variable name 'total' to 'running_sum' everywhere:\n\ndef add_all(values):\n    total = 0\n    for v in values:\n        if v is None:\n            continue\n        total += v\n    return total\n\ndef mean(values):\n    total = add_all(values)\n    count = len([v for v in values if v is not None])\n    return total / count if count else 0.0\n", "low"),
         ("prose", "Explain in three short paragraphs how a refrigerator keeps food cold.", "low")]
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
PROBE = {"messages": [{"role": "user", "content": "List the planets of the solar system in order from the Sun, with one short fact about each."}],
         "temperature": 0, "max_tokens": 200, "cache_prompt": False}
STOP = {"flag": False, "why": ""}
CHILD = {"proc": None}

def records(n, seed):  # deterministic filler data
    r = random.Random(seed)
    w = "copper wire crates audit Denver ledger harbor valve signal orchard tunnel beacon quartz meadow".split()
    return ["Record %04d: the %s depot shipped %d %s units on day %d; audit code %s%d%s." % (
        i, r.choice(w), r.randint(2, 99), r.choice(w), r.randint(1, 28), r.choice("KQXZ"), r.randint(1, 9), r.choice("ABCD"))
        for i in range(1, n + 1)]

def longdoc(n):  # ~27 tokens per line: 200 lines ~5.5K tokens, 600 lines ~16K
    lines = records(n, 7)
    return "\n".join(lines) + "\n\nWhich record number mentions audit code %s? Reply with only the number." % lines[6].split()[-1].rstrip(".")
SYS = "You answer questions about the shipping log below. Answer in one short sentence.\n\n" + "\n".join(records(120, 3))

def log(msg):
    print(time.strftime("%H:%M:%SZ", time.gmtime()), msg, flush=True)

def sh(cmd, timeout=120):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return subprocess.CompletedProcess(cmd, 99, "", str(e))

def http(path, body=None, port=PORT, timeout=7200):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def healthy(port=PORT):
    try:
        return http("/health", port=port, timeout=5).get("status") == "ok"
    except Exception:
        return False

def port_free(port):
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # ignore TIME_WAIT leftovers; fails only if something listens
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()

def jarvis_tps():
    try:
        return float(http("/v1/chat/completions", PROBE, port=JPORT, timeout=300)["timings"]["predicted_per_second"])
    except Exception as e:
        log("Jarvis probe failed: %s" % e)
        return None

class Probe(threading.Thread):  # probes Jarvis during the tests; sets STOP after two slow probes in a row
    def __init__(self, base):
        super().__init__(daemon=True)
        self.base, self.vals, self.run_flag = base, [], True
    def run(self):
        low = 0
        while self.run_flag and not STOP["flag"]:
            for _ in range(PROBE_EVERY):
                if not self.run_flag or STOP["flag"]:
                    return
                time.sleep(1)
            v = jarvis_tps()
            self.vals.append(v)
            low = low + 1 if (v is not None and v < LIMIT * self.base) else 0
            if low >= 2:
                STOP["flag"], STOP["why"] = True, "Jarvis below %d%% of %.1f t/s twice" % (LIMIT * 100, self.base)
                log("STOP: " + STOP["why"])
                stop_child()

def shards(model):
    m = re.match(r"(.*)-00001-of-(\d{5})\.gguf$", model)
    return sorted(glob.glob("%s-*-of-%s.gguf" % (m.group(1), m.group(2)))) if m else [model]

def cached_gib(files):  # page-cache bytes of the files, via util-linux fincore (None if unavailable)
    r = sh(["fincore", "--bytes", "--noheadings", "--output", "RES"] + files)
    try:
        return round(sum(int(x) for x in r.stdout.split()) / 2**30, 1) if r.returncode == 0 else None
    except ValueError:
        return None

def evict(files):  # drop these files' clean pages from the page cache (pages mapped by a running process stay)
    for f in files:
        fd = os.open(f, os.O_RDONLY)
        try:
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
        finally:
            os.close(fd)

def meminfo(key):
    for line in open("/proc/meminfo"):
        if line.startswith(key + ":"):
            return int(line.split()[1]) / 2**20
    return 0.0

def rss_gib(pid):
    try:
        for line in open("/proc/%d/status" % pid):
            if line.startswith("VmRSS:"):
                return round(int(line.split()[1]) / 2**20, 1)
    except OSError:
        pass
    return None

def numa_mb(pid):  # per-node MB of the server process, from numastat (None if unavailable)
    r = sh(["numastat", "-p", str(pid)], 60)
    tot = [l for l in r.stdout.splitlines() if l.startswith("Total")]
    return tot[-1].split()[1:] if r.returncode == 0 and tot else None

def stop_child():
    p = CHILD["proc"]
    if p and p.poll() is None:
        p.terminate()
        try:
            p.wait(timeout=90)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(timeout=30)

def complete(prompt, n, probs=False, cache=False):
    b = {"prompt": prompt, "n_predict": n, "temperature": 0, "top_k": 1, "seed": 42, "cache_prompt": cache}
    if probs:
        b["n_probs"] = 2
    r = http("/completion", b)
    t = r.get("timings", {})
    out = {"text": r.get("content", ""), "tg": float(t.get("predicted_per_second", 0)), "pp": float(t.get("prompt_per_second", 0)),
           "np": int(t.get("prompt_n", 0)), "ng": int(t.get("predicted_n", 0)), "pms": float(t.get("prompt_ms", 0)),
           "dn": int(t.get("draft_n", t.get("n_draft", 0)) or 0), "da": int(t.get("draft_n_accepted", t.get("n_draft_accepted", 0)) or 0)}
    if probs:
        out["toks"] = [[p.get("bytes", []), [[q.get("bytes", []), q.get("logprob", 0.0)] for q in p.get("top_logprobs", [])[:2]]]
                       for p in r.get("completion_probabilities", [])]
    return out

def compare(ref, text):  # IDENTICAL / NEAR-TIE / DIVERGED (with gap) / PREFIX, using the reference's top-2 logprobs
    a, b = ref["text"].encode(), text.encode()
    d = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), None)
    if d is None:
        if len(a) == len(b):
            return ("IDENTICAL", 0.0)
        d = min(len(a), len(b))
    pos = 0
    for tb, top in ref.get("toks", []):
        if pos + len(tb) > d:
            gap = top[0][1] - top[1][1] if len(top) >= 2 else 99.0
            return ("NEAR-TIE" if gap <= 0.10 else "DIVERGED", round(gap, 3))
        pos += len(tb)
    return ("PREFIX", 99.0)

def chat(msgs, n):
    r = http("/v1/chat/completions", {"messages": msgs, "max_tokens": n, "temperature": 0, "top_k": 1, "seed": 42,
                                      "cache_prompt": True, "chat_template_kwargs": {"reasoning_effort": "low"}})
    t, u = r.get("timings", {}), r.get("usage", {})
    return (r["choices"][0]["message"].get("content") or ""), int(t.get("prompt_n", -1)), int(u.get("prompt_tokens", -1))

def cache_test(logpath):
    q1, q2, q3 = "Which depot shipped units in Record 0005?", "What is the audit code of Record 0012?", "And in Record 0006?"
    a1, p1, t1 = chat([{"role": "system", "content": SYS}, {"role": "user", "content": q1}], 128)
    _, p2, t2 = chat([{"role": "system", "content": SYS}, {"role": "user", "content": q2}], 128)
    _, p3, t3 = chat([{"role": "system", "content": SYS}, {"role": "user", "content": q1}, {"role": "assistant", "content": a1},
                      {"role": "user", "content": q3}], 128)
    txt = open(logpath, errors="replace").read()
    full = len(re.findall(r"(?i)forcing full prompt re-processing", txt))
    rest = len(re.findall(r"(?i)restor\w*[^\n]*checkpoint", txt))
    sizes = [float(x) for x in re.findall(r"created context checkpoint[^\n]*size = ([\d.]+) MiB", txt)]
    ok = 0 <= p2 <= 0.25 * max(t2, 1) and 0 <= p3 <= 0.5 * max(t3, 1)
    return {"turns": [[p1, t1], [p2, t2], [p3, t3]], "full_reprocess_lines": full, "restore_lines": rest,
            "checkpoints": [len(sizes), max(sizes) if sizes else 0.0], "pass": ok}

def par_test(prompt):
    one = complete(prompt, 128)
    res, t0 = [], time.time()
    th = [threading.Thread(target=lambda: res.append(complete(prompt, 128))) for _ in range(2)]
    [t.start() for t in th]
    [t.join() for t in th]
    wall = time.time() - t0
    return {"single_tg": round(one["tg"], 2), "two_aggregate_tg": round(sum(r["ng"] for r in res) / wall, 2) if len(res) == 2 else None}

def slot_test(prompt, prior=None):  # needs --slot-save-path; saves slot 0, erases it, restores it, re-sends the prompt
    a = prior or complete(prompt, 16, cache=True)  # prior = the prefill test's result (same prompt, already cached)
    sv = http("/slots/0?action=save", {"filename": "cpu_test_slot.bin"})
    http("/slots/0?action=erase", {})
    rs = http("/slots/0?action=restore", {"filename": "cpu_test_slot.bin"})
    b = complete(prompt, 16, cache=True)
    return {"prefill_s": round(a["pms"] / 1000, 1), "tokens": a["np"], "save_s": round(sv["timings"]["save_ms"] / 1000, 1),
            "gib": round(sv["n_written"] / 2**30, 2), "restore_s": round(rs["timings"]["restore_ms"] / 1000, 1),
            "after_restore_prompt_n": b["np"], "after_restore_prompt_s": round(b["pms"] / 1000, 1), "same_answer": a["text"] == b["text"]}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--bin", default="stock")
    ap.add_argument("--model", default="fn")
    ap.add_argument("--numa", default="il", choices=sorted(NUMA))
    ap.add_argument("--tests", default="speed")
    ap.add_argument("--ref")
    ap.add_argument("--make-ref")
    ap.add_argument("--warm", type=int, default=1)
    ap.add_argument("--evict", action="store_true")
    ap.add_argument("--no-probe", action="store_true")
    ap.add_argument("--ctx", default="32768")
    ap.add_argument("--prefill-lines", type=int, default=200)
    ap.add_argument("--ram-need-gib", type=float, help="override the free-RAM precondition (e.g. a model streamed from disk)")
    ap.add_argument("--max-min", type=int, default=170)
    ap.add_argument("--check", action="store_true")
    argv = sys.argv[1:]
    cut = argv.index("--") if "--" in argv else len(argv)
    a, extra = ap.parse_args(argv[:cut]), argv[cut + 1:]
    tests = [t for t in a.tests.split(",") if t]
    binp, model = BINS.get(a.bin, a.bin), MODELS.get(a.model, a.model)
    files = shards(model)
    need = [binp] + files + [extra[i + 1] for i, x in enumerate(extra[:-1]) if x in ("-md", "--model-draft")]
    mirror = "mirror" in extra
    gib_need = sum(os.path.getsize(f) for f in files if os.path.exists(f)) / 2**30 * (2 if mirror else 1) + MARGIN
    if a.ram_need_gib is not None:
        gib_need = a.ram_need_gib
    busy = [u for u in sh(["systemctl", "list-units", "--type=service", "--state=active", "--no-legend", "--plain"]).stdout.split()
            if BUSY.match(u)]
    base = ["-m", model, "-c", a.ctx, "--host", "127.0.0.1", "--port", str(PORT), "--jinja"]
    if not any(x in extra for x in ("-np", "--parallel")):
        base += ["--parallel", "1"]
    cmd = NUMA[a.numa] + [binp] + base + extra
    problems = ["missing " + f for f in need if not os.path.exists(f)]
    problems += ["busy units: " + " ".join(busy)] if busy else []
    problems += ["port %d in use" % PORT] if not port_free(PORT) else []
    problems += ["Jarvis (llama-server) not active"] if not a.no_probe and sh(["systemctl", "is-active", "--quiet", "llama-server"]).returncode else []
    problems += ["MemAvailable %.0f GiB < needed %.0f GiB" % (meminfo("MemAvailable"), gib_need)] if meminfo("MemAvailable") < gib_need else []
    problems += ["--ref file missing"] if a.ref and not os.path.exists("%s/%s.json" % (REFDIR, a.ref)) else []
    known = ("speed", "prefill", "cache", "par", "qual", "slot")
    problems += ["unknown tests: %s" % [t for t in tests if t not in known]] if any(t not in known for t in tests) else []
    problems += ["slot test needs --slot-save-path in the server flags"] if "slot" in tests and "--slot-save-path" not in extra else []
    print("command: " + " ".join(cmd)[:1500])
    print("model files: %d, %.1f GiB (need %.0f GiB free RAM) | page cache now %s GiB" % (
        len(files), sum(os.path.getsize(f) for f in files if os.path.exists(f)) / 2**30, gib_need, cached_gib(files)))
    if problems:
        sys.exit("NOT STARTED: " + "; ".join(problems))
    if a.check:
        print("CHECK OK (nothing started)")
        return
    out = time.strftime("%s/%s/%%Y%%m%%d-%%H%%M%%S" % (OUTROOT, a.label), time.gmtime())
    os.makedirs(out, exist_ok=True)
    os.makedirs(REFDIR, exist_ok=True)
    R = {"label": a.label, "cmd": cmd, "tests": tests, "start_utc": os.path.basename(out),
         "sys": {k: open(p).read().strip() for k, p in (("numa_balancing", "/proc/sys/kernel/numa_balancing"),
                 ("thp", "/sys/kernel/mm/transparent_hugepage/enabled")) if os.path.exists(p)}}
    t_start, probe, jbase = time.time(), None, None
    try:
        if a.evict:
            before = cached_gib(files)
            evict(files)
            R["evict"] = [before, cached_gib(files)]
            log("page cache of model files: %s -> %s GiB" % tuple(R["evict"]))
        if not a.no_probe:
            b = [jarvis_tps() for _ in range(3)]
            R["jarvis_before"] = b
            jbase = statistics.median([v for v in b if v] or [0])
            if not jbase:
                raise RuntimeError("Jarvis did not answer the baseline probes")
            log("Jarvis baseline %.2f t/s" % jbase)
        env = dict(os.environ, CUDA_VISIBLE_DEVICES="")
        logf = open(out + "/server.log", "w")
        t0 = time.time()
        CHILD["proc"] = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, env=env)
        while not healthy():
            if STOP["flag"] or CHILD["proc"].poll() is not None or time.time() - t0 > 2700:
                raise RuntimeError("server did not come up (see server.log)")
            time.sleep(5)
        R["load_s"] = round(time.time() - t0)
        log("server up after %d s" % R["load_s"])
        if jbase:
            probe = Probe(jbase)
            probe.start()
        for i in range(a.warm):
            complete("Warm-up %d: say hello." % i, 32)
        R["rss_gib"], R["numa_mb"] = rss_gib(CHILD["proc"].pid), numa_mb(CHILD["proc"].pid)
        ref = json.load(open("%s/%s.json" % (REFDIR, a.ref))) if a.ref else None
        prompts = (ref or {}).get("prompts")
        if not prompts:
            def templ(text, effort):
                return http("/apply-template", {"messages": [{"role": "user", "content": text}],
                                                "chat_template_kwargs": {"reasoning_effort": effort}})["prompt"]
            prompts = {k: templ(t, e) for k, t, e in SPEED}
            prompts["long"] = templ(longdoc(200), "low")
            prompts.update({"q%d" % i: templ(q, "low") for i, (q, _) in enumerate(QUAL)})
        longp = prompts["long"]  # the standard 200-line document; a custom length is never stored in a reference
        if a.prefill_lines != 200 and ("prefill" in tests or "slot" in tests):
            longp = http("/apply-template", {"messages": [{"role": "user", "content": longdoc(a.prefill_lines)}],
                                             "chat_template_kwargs": {"reasoning_effort": "low"}})["prompt"]
        R["prompts"] = prompts
        prefill_res = None
        def timeleft():
            return not STOP["flag"] and time.time() - t_start < (a.max_min - 10) * 60
        if "speed" in tests:
            R["speed"] = {}
            for k, _, _ in SPEED:
                if not timeleft():
                    break
                r = complete(prompts[k], 256)
                if a.make_ref:
                    r2 = complete(prompts[k], 256, probs=True)
                    r["toks"], r["rerun_same"] = r2["toks"], r2["text"] == r["text"]
                if ref and k in ref.get("speed", {}):
                    r["vs_ref"] = compare(ref["speed"][k], r["text"])
                R["speed"][k] = r
                log("  %-9s tg %6.2f pp %6.1f gen %d draft %d/%d %s" % (k, r["tg"], r["pp"], r["ng"], r["da"], r["dn"], r.get("vs_ref", "")))
        if "prefill" in tests and timeleft():
            r = complete(longp, 32, cache=True)
            R["prefill"] = {"pp": round(r["pp"], 2), "prompt_n": r["np"], "tg_at_depth": round(r["tg"], 2)}
            prefill_res = r
            log("  prefill %.2f t/s over %d tokens, then decode %.2f t/s at that depth" % (r["pp"], r["np"], r["tg"]))
        if "cache" in tests and timeleft():
            R["cache"] = cache_test(out + "/server.log")
            log("  cache: %s" % R["cache"])
        if "par" in tests and timeleft():
            R["par"] = par_test(prompts["prose"])
            log("  parallel: %s" % R["par"])
        if "slot" in tests and timeleft():
            R["slot"] = slot_test(longp, prefill_res)
            log("  slot save/restore: %s" % R["slot"])
        if "qual" in tests and timeleft():
            R["qual"] = []
            for i, (q, rx) in enumerate(QUAL):
                if not timeleft():
                    break
                r = complete(prompts["q%d" % i], 768)
                r["ok"] = "</think>" in r["text"] and bool(re.search(rx, r["text"].split("</think>")[-1]))
                R["qual"].append({"ok": r["ok"], "ng": r["ng"], "tail": r["text"][-80:]})
    except Exception as e:
        R["error"] = str(e)
        log("ERROR: %s" % e)
    finally:
        if probe:
            probe.run_flag = False
            R["jarvis_during"] = probe.vals
        stop_child()
        if jbase and not STOP["why"].startswith("stop requested"):
            R["jarvis_after"] = [jarvis_tps() for _ in range(3)]
        R["stopped"] = STOP["why"]
        if a.make_ref and len(R.get("speed", {})) == len(SPEED) and all(r.get("rerun_same") for r in R["speed"].values()) \
                and not R.get("error") and not STOP["flag"]:
            json.dump({"prompts": R["prompts"], "speed": R["speed"], "cmd": cmd, "made": R["start_utc"]},
                      open("%s/%s.json" % (REFDIR, a.make_ref), "w"))
            R["ref_saved"] = a.make_ref
        json.dump({k: v for k, v in R.items() if k != "prompts"}, open(out + "/results.json", "w"), indent=1)
        s = summary(R)
        open(out + "/summary.txt", "w").write(s)
        print(s, flush=True)

def med(xs):
    xs = [x for x in (xs or []) if x]
    return "%.1f" % statistics.median(xs) if xs else "-"

def summary(R):
    L = ["cpu_test %s @ %s UTC | numa_balancing %s | THP %s" % (R["label"], R["start_utc"], R["sys"].get("numa_balancing"),
         re.sub(r".*\[(\w+)\].*", r"\1", R["sys"].get("thp", "?")))]
    L.append("command: " + " ".join(R["cmd"])[:600])
    L.append("load %s s | RSS %s GiB | per-node MB %s | evict %s" % (R.get("load_s"), R.get("rss_gib"), R.get("numa_mb"), R.get("evict")))
    sp = R.get("speed", {})
    if sp:
        tg = [sp[k]["tg"] for k in sp]
        dn, da = sum(sp[k]["dn"] for k in sp), sum(sp[k]["da"] for k in sp)
        L.append("decode t/s %s | mean %.2f | draft accepted %s" % (" / ".join("%s %.2f" % (k, sp[k]["tg"]) for k in sp),
                 sum(tg) / len(tg), "%d/%d = %.3f" % (da, dn, da / dn) if dn else "-"))
        kinds = [sp[k]["vs_ref"] for k in sp if "vs_ref" in sp[k]]
        if kinds:
            L.append("vs reference: " + ", ".join("%s %s%s" % (k, sp[k]["vs_ref"][0], "" if sp[k]["vs_ref"][0] == "IDENTICAL" else
                     " gap %.3f" % sp[k]["vs_ref"][1]) for k in sp if "vs_ref" in sp[k]))
        if any("rerun_same" in sp[k] for k in sp):
            L.append("reference re-run identical: %d/%d%s" % (sum(1 for k in sp if sp[k].get("rerun_same")), len(sp),
                     " | saved as reference " + R["ref_saved"] if R.get("ref_saved") else " | reference NOT saved"))
    if "prefill" in R:
        L.append("prefill %.2f t/s over %d tokens | decode after it %.2f t/s" % (R["prefill"]["pp"], R["prefill"]["prompt_n"],
                 R["prefill"].get("tg_at_depth", 0)))
    if "cache" in R:
        c = R["cache"]
        L.append("prompt cache: processed/total per turn %s | full re-processing lines %d | checkpoint restores %d, created %d (largest %.1f MiB) | %s" % (
            " ".join("%d/%d" % tuple(t) for t in c["turns"]), c["full_reprocess_lines"], c["restore_lines"], c["checkpoints"][0],
            c["checkpoints"][1], "PASS" if c["pass"] else "FAIL"))
    if "par" in R:
        L.append("2 slots: single %s t/s, two at once %s t/s total" % (R["par"]["single_tg"], R["par"]["two_aggregate_tg"]))
    if "slot" in R:
        x = R["slot"]
        L.append("slot: first prefill %s s for %s tokens | save %s s, %s GiB | restore %s s | after restore %s tokens in %s s | same answer %s" % (
            x["prefill_s"], x["tokens"], x["save_s"], x["gib"], x["restore_s"], x["after_restore_prompt_n"], x["after_restore_prompt_s"], x["same_answer"]))
    if "qual" in R:
        L.append("quality set: %d/%d correct" % (sum(q["ok"] for q in R["qual"]), len(R["qual"])))
    if "jarvis_before" in R:
        d = [v for v in R.get("jarvis_during", []) if v]
        L.append("Jarvis t/s median before %s | during %s (lowest %s, %d probes) | after %s" % (
            med(R["jarvis_before"]), med(d), "%.1f" % min(d) if d else "-", len(d), med(R.get("jarvis_after"))))
    if R.get("stopped"):
        L.append("STOPPED EARLY: " + R["stopped"])
    if R.get("error"):
        L.append("ERROR: " + R["error"])
    return "\n".join(L)[:3800] + "\n"

def on_term(signum, frame):
    STOP["flag"], STOP["why"] = True, STOP["why"] or "stop requested (signal %d)" % signum
    log("stop requested: stopping the test server")
    threading.Thread(target=stop_child, daemon=True).start()

signal.signal(signal.SIGTERM, on_term)
signal.signal(signal.SIGINT, on_term)
if __name__ == "__main__":
    main()
