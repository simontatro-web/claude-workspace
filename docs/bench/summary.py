#!/usr/bin/env python3
# Prints a table from llama-bench jsonl results.
# Usage: python3 ~/bench/summary.py ~/bench/results/<label>/*.jsonl
import json, sys
rows = []
for path in sys.argv[1:]:
    for line in open(path, errors="replace"):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
if not rows:
    sys.exit("no results found")
print("%-5s %6s %6s %6s %4s %5s %5s %5s %5s %4s %9s %8s" % (
    "test", "prompt", "gen", "depth", "thr", "b", "ub", "ctk", "ctv", "fa", "t/s", "+/-"))
for r in rows:
    test = "pp" if r.get("n_prompt", 0) and not r.get("n_gen", 0) else ("tg" if r.get("n_gen", 0) and not r.get("n_prompt", 0) else "pg")
    print("%-5s %6s %6s %6s %4s %5s %5s %5s %5s %4s %9.2f %8.2f" % (
        test, r.get("n_prompt"), r.get("n_gen"), r.get("n_depth", 0), r.get("n_threads"),
        r.get("n_batch"), r.get("n_ubatch"), r.get("type_k"), r.get("type_v"),
        str(r.get("flash_attn")), float(r.get("avg_ts", 0)), float(r.get("stddev_ts", 0))))
print("model: %s  size: %.1f GiB  params: %.1fB  backend: %s" % (
    rows[0].get("model_type"), rows[0].get("model_size", 0) / 2**30,
    rows[0].get("model_n_params", 0) / 1e9, rows[0].get("backends")))
