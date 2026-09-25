#!/usr/bin/env python3
"""Create (or reset) the live acceptance task in ~/ctxtest: 25 files, 25 edits.

Each file is ~50 lines of filler (so reading it costs context) with one line
"VALUE: old-NN". The task: for each NN, read the file, change that line to
"VALUE: new-NN-<code>", verify, commit "edit NN". check_task.py grades it.

Run:  python3 setup_task.py        (refuses if ~/ctxtest exists; add --reset to wipe it)
"""
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys

ROOT = os.path.expanduser("~/ctxtest")
WORDS = ("alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november "
         "oscar papa quebec romeo sierra tango uniform victor whiskey xray yankee zulu").split()

if os.path.exists(ROOT):
    if "--reset" not in sys.argv:
        sys.exit(f"{ROOT} exists; run with --reset to wipe and recreate it")
    shutil.rmtree(ROOT)
os.makedirs(ROOT)
rng = random.Random(2026)
expected = {}
for n in range(1, 26):
    nn = f"{n:02d}"
    code = hashlib.sha256(f"ctxtest-{nn}".encode()).hexdigest()[:6]
    lines = []
    for i in range(50):
        lines.append(f"{nn}.{i:02d} " + " ".join(rng.choice(WORDS) for _ in range(12)))
    pos = rng.randrange(10, 40)
    lines.insert(pos, f"VALUE: old-{nn}")
    with open(os.path.join(ROOT, f"f{nn}.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    new_lines = list(lines)
    new_lines[pos] = f"VALUE: new-{nn}-{code}"
    expected[nn] = {"code": code, "sha": hashlib.sha256(("\n".join(new_lines) + "\n").encode()).hexdigest()}

steps = "\n".join(
    f"{n}. Edit {n:02d}: in f{n:02d}.txt change the line `VALUE: old-{n:02d}` to `VALUE: new-{n:02d}-{expected[f'{n:02d}']['code']}`."
    for n in range(1, 26))
task = f"""# Acceptance task (context proxy test)

Work in ~/ctxtest. Do the 25 edits below IN ORDER. For EACH edit, exactly this, as separate tool calls:
  a) read the whole file with `cat -n ~/ctxtest/fNN.txt` (yes, the whole file every time);
  b) change only that one line, then verify with `grep -n VALUE ~/ctxtest/fNN.txt` and commit with
     `git -C ~/ctxtest commit -am "edit NN"` (NN = two digits), all in one command;
  c) after edits 05, 10, 15 and 20, update the RESUME HERE block in ~/jarvis-build/PROGRESS.md:
     "Acceptance task in ~/ctxtest: last committed edit NN; exact next action: edit NN+1".
Never redo an edit that is already committed: `git -C ~/ctxtest log --oneline` is the truth.
Do not change anything else. When all 25 are committed, run `git -C ~/ctxtest log --oneline | wc -l` and stop.

{steps}
"""
with open(os.path.join(ROOT, "TASK.md"), "w") as f:
    f.write(task)
with open(os.path.join(ROOT, ".expected.json"), "w") as f:
    json.dump(expected, f)
with open(os.path.join(ROOT, ".gitignore"), "w") as f:
    f.write(".expected.json\n")
run = lambda *a: subprocess.run(["git", "-C", ROOT, *a], check=True, capture_output=True)
run("init", "-q")
run("add", "-A")
run("-c", "user.name=ctxtest", "-c", "user.email=ctxtest@localhost", "commit", "-q", "-m", "setup")
print(f"ready: {ROOT} (25 files, TASK.md, 1 setup commit)")
