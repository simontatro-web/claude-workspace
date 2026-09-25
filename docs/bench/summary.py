#!/usr/bin/env python3
# Prints a table from llama-bench jsonl results. Columns = the settings that vary between tests.
# Usage: python3 ~/bench/summary.py ~/bench/results/<label>/*.jsonl
# Also reads ik_llama.cpp's "-o json" output (one JSON array per file).
import json, sys
rows = []
for path in sys.argv[1:]:
    text = open(path, errors="replace").read()
    start = text.find("[")
    if start != -1 and not text.lstrip().startswith("{"):
        try:
            rows.extend(r for r in json.loads(text[start:text.rfind("]") + 1]) if isinstance(r, dict))
            continue
        except ValueError:
            pass
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
if not rows:
    sys.exit("no results found")
skip = {"avg_ns", "stddev_ns", "avg_ts", "stddev_ts", "samples_ns", "samples_ts", "test_time",
        "build_commit", "build_number", "cpu_info", "gpu_info", "model_filename"}
keys = []
for r in rows:
    for k in r:
        if k not in skip and k not in keys and not isinstance(r[k], (list, dict)):
            keys.append(k)
vary = [k for k in keys if len({str(r.get(k)) for r in rows}) > 1]
for k in ("n_prompt", "n_gen", "n_depth"):
    if k not in vary:
        vary.insert(0, k)
same = {k: rows[0].get(k) for k in keys if k not in vary}
print("fixed: " + ", ".join("%s=%s" % (k, v) for k, v in same.items()))
w = [max(len(k), max(len(str(r.get(k))) for r in rows)) for k in vary]
print("  ".join(k.rjust(n) for k, n in zip(vary, w)) + "        t/s      +/-")
for r in rows:
    print("  ".join(str(r.get(k)).rjust(n) for k, n in zip(vary, w)) +
          "  %9.2f  %7.2f" % (float(r.get("avg_ts", 0)), float(r.get("stddev_ts", 0))))
