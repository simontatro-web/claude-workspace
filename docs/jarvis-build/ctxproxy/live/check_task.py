#!/usr/bin/env python3
"""Grade the live acceptance run in ~/ctxtest (gate 2 of STRESS-PLAN ACCEPTANCE).

PASS only if: exactly 25 "edit NN" commits after "setup", in order 01..25, each
exactly once, each touching only fNN.txt; every file ends exactly as expected;
the working tree is clean. Also lists the proxy's compactions during the run.

Run:  python3 check_task.py
"""
import json
import os
import subprocess
import sys

ROOT = os.path.expanduser("~/ctxtest")
EVENTS = os.path.expanduser("~/jarvis-build/ctxproxy/events.jsonl")


def git(*a):
    return subprocess.run(["git", "-C", ROOT, *a], capture_output=True, text=True, check=True).stdout


problems = []
expected = json.load(open(os.path.join(ROOT, ".expected.json")))
log = git("log", "--reverse", "--format=%H %ct %s").strip().splitlines()
subjects = [ln.split(" ", 2)[2] for ln in log]
if not subjects or subjects[0] != "setup":
    problems.append("first commit is not 'setup'")
edits = subjects[1:]
want = [f"edit {n:02d}" for n in range(1, 26)]
if edits != want:
    dup = sorted({s for s in edits if edits.count(s) > 1})
    missing = [w for w in want if w not in edits]
    extra = [s for s in edits if s not in want]
    problems.append(f"commits wrong: {len(edits)} edit commits; duplicates {dup}; missing {missing}; "
                    f"unexpected {extra}; in order: {edits == sorted(edits)}")
for ln in log[1:]:
    h, _, subj = ln.split(" ", 2)
    files = git("show", "--name-only", "--format=", h).split()
    nn = subj[-2:]
    if files != [f"f{nn}.txt"]:
        problems.append(f"commit '{subj}' touched {files}")
import hashlib  # noqa: E402
for nn, e in expected.items():
    data = open(os.path.join(ROOT, f"f{nn}.txt"), "rb").read()
    if hashlib.sha256(data).hexdigest() != e["sha"]:
        problems.append(f"f{nn}.txt content is not as expected")
status = git("status", "--porcelain").strip()
if status:
    problems.append("working tree not clean: " + status.replace("\n", "; "))

start = int(log[0].split()[1]) if log else 0
comps = []
if os.path.exists(EVENTS):
    for line in open(EVENTS):
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("ts", 0) >= start and ev.get("action") == "compact":
            comps.append(ev)
print(f"edit commits: {len(edits)}/25; compactions during the run: {len(comps)}")
for ev in comps:
    print(f"  compact {ev.get('tok_before')} -> {ev.get('tok_after')} tokens, handoff {ev.get('handoff')}")
if problems:
    print("FAIL")
    for p in problems:
        print("  - " + p)
    sys.exit(1)
print("PASS" + ("" if comps else "  (but NO compaction happened: this run does not count for gate 4)"))
