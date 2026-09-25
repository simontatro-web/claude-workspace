#!/usr/bin/env python3
"""Summarise events.jsonl: what the proxy did, how accurate its count is, how long
Jarvis's replies are (to set RESERVE), and whether the cache survives compaction.

Run:  ~/jarvis-build/venv/bin/python ~/jarvis-build/ctxproxy/report.py [--since-min N]
"""
import json
import os
import sys
import time
from collections import Counter

D = os.path.dirname(os.path.abspath(__file__))
since = 0
if "--since-min" in sys.argv:
    since = time.time() - 60 * float(sys.argv[sys.argv.index("--since-min") + 1])

ev = []
for name in ("events.jsonl.1", "events.jsonl"):
    p = os.path.join(os.environ.get("CTXPROXY_STATE_DIR", D), name)
    if os.path.exists(p):
        for line in open(p):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("ts", 0) >= since:
                ev.append(e)
if not ev:
    sys.exit("no events yet")


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * q))] if xs else None


print(f"{len(ev)} chat requests, {time.strftime('%m-%d %H:%M', time.localtime(ev[0]['ts']))} "
      f"to {time.strftime('%m-%d %H:%M', time.localtime(ev[-1]['ts']))}")
print("actions:", dict(Counter(e.get("action") for e in ev)), "| warned:", sum(1 for e in ev if e.get("warned")))
errs = Counter(e["error"] for e in ev if e.get("error"))
print("errors:", dict(errs) if errs else "none")

gaps = []
for e in ev:
    real = (e.get("up_prompt_n") or 0) + (e.get("up_cache_n") or 0)
    ours = e.get("tok_after")
    if real > 2000 and ours:
        gaps.append((ours - real) / real * 100)
if gaps:
    print(f"count accuracy vs llama-server: median {pct(gaps, .5):+.1f}%, worst under {min(gaps):+.1f}%, "
          f"worst over {max(gaps):+.1f}% ({len(gaps)} requests). Under-counting is the dangerous side.")

out = [e["up_predicted_n"] for e in ev if e.get("up_predicted_n")]
if out:
    p99 = pct(out, .99)
    print(f"reply length (thinking+answer) per request: median {pct(out, .5)}, p95 {pct(out, .95)}, "
          f"p99 {p99}, max {max(out)} ({len(out)} requests)")
    print(f"  -> suggested CTXPROXY_RESERVE = {int((max(p99, 1000) + 500 + 499) // 500 * 500)} (now default 6000)")

peak = max((e.get("up_prompt_n") or 0) + (e.get("up_cache_n") or 0) + (e.get("up_predicted_n") or 0) for e in ev)
print(f"largest prompt+reply seen by llama-server: {peak} of 24576")

sticky = [e for e in ev if e.get("action") == "sticky" and e.get("up_prompt_n") is not None]
if sticky:
    re_read = [e["up_prompt_n"] / max(1, e["up_prompt_n"] + (e.get("up_cache_n") or 0)) * 100 for e in sticky]
    print(f"after compaction, share of prompt re-read: median {pct(re_read, .5):.0f}% (low is good; ~100% means the cache is lost)")

comp = [e for e in ev if e.get("action") == "compact"]
for e in comp:
    print(f"compact {time.strftime('%H:%M:%S', time.localtime(e['ts']))}: {e.get('tok_before')} -> "
          f"{e.get('tok_after')} tokens, handoff: {e.get('handoff')}")
