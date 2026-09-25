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
