# Fast-house model download — state and fixes (Sep 24 2026)

The overnight pull of models + corpora to `D:\models` on the fast-house PC (4 TB drive),
driven by `D:\models\CHAIN.ps1`. Full plan is in `MANIFEST.md` (the upload); this file is
the working state and the fixes applied during the Sep 24 session.

## How CHAIN.ps1 works

- Python venv: `D:\models\.venv\Scripts\python.exe`. Logs to `D:\models\_logs\chain.log`.
- **First pass** runs 5 scripts in priority order: `pull.py, pull_extras.py, pull_hq.py,
  pull_addendum.py, pull_corpus.py`.
- **Watcher loop** then re-runs **every `pull*.py` on the drive**, alphabetically, every 30 min
  for 36 hours. Finished items are instant (marker files in `_logs/`). This is how the later
  scripts (`pull_corpus2, pull_data, pull_data2, pull_wants, pull_rsi, pull_wheels, pull_orch,
  pull_research, pull_one`) get run — they are NOT in the first pass.
- Ends with `verify.py --size-only` then full sha256. Stop early with a `D:\models\STOP-CHAIN.txt` file.
- Run it: `powershell -NoProfile -ExecutionPolicy Bypass -File D:\models\CHAIN.ps1`
  (fresh shells block `.ps1`; `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` also works).
- All 14 pull scripts confirmed present on the drive Sep 24.

## State as of Sep 24 ~14:00Z

- **Done (~1,821 GB on disk):** all of `pull.py` (uncensored 27B, both Flash-Next quant lines,
  GLM-5.3-Flash, full GLM-5.3, MiMo, gpt-oss-20b), all `pull_extras.py` (Wan/LTX/Hunyuan video,
  Z-Image, Qwen3-Coder-Next, embed/rerank/OCR/ASR slots), most `pull_hq.py`.
- **Running:** `pull_addendum.py` (~238 GB: 3 vision mmproj files, Qwen3-Embedding-4B, jina-code,
  Qwen3-VL-32B, Kokoro, the ~206 GB audio.cpp hub).
- **Queued for the watcher:** corpus (~752 GB), corpus2 (~420 GB: PMC, PubMed, devdocs, refs),
  data (88), wants (85), rsi (36), data2 (128), wheels (10-15), orch (55).
- Plan totals ~3,500 GB into a 4,001 GB drive → **~425-515 GB free at the end**. No free-space
  guard in any script; if tight, drop order is Khan Academy (168) → Wikipedia-maxi (119) → Gutenberg (206).

## Fixes applied this session

### 1. `pull_addendum.py` aborted (`code=3`, "Nothing downloaded")

Cause: a preflight requires every include glob to match ≥1 file. The `audio-cpp/audio.cpp-gguf`
repo has no `.patch` files, so the `*.patch` pattern matched nothing and aborted the whole script
before any download. Fix: removed `"*.patch"` from that repo's include list (line 46).

### 2. Both corpus scripts: `certificate has expired` on every Kiwix ZIM

Cause **not** a bad mirror and **not** stale certifi (certifi 2026.7.22 is current). The scripts
use raw `urllib`, whose default HTTPS verification uses the **Windows system cert store**, which on
this box is stale — it still chains Let's Encrypt certs through the expired DST Root CA X3, so any
LE-served host reads as "expired". `download.kiwix.org` 302-redirects file requests to mirrors
(e.g. `wi.mirror.driftle.ss`) that use LE certs, so every file failed. HuggingFace downloads were
fine because `huggingface_hub` uses certifi, not the Windows store.

Confirmed: `urlopen(..., context=ssl.create_default_context(cafile=certifi.where()))` returns
`OK 200` on the redirected mirror where the default context fails.

Fix applied to **`pull_corpus.py`** and **`pull_corpus2.py`** — added at the top:
```python
import ssl, certifi
_SSL = ssl.create_default_context(cafile=certifi.where())
```
and passed `context=_SSL` to every `urllib.request.urlopen(...)` call (the HEAD and the download
in pull_corpus; the index HEAD in pull_corpus2, whose downloads reuse pull_corpus's patched fn).
Backups saved as `*.py.bak`.

**This fix will recur on any fresh copy of these scripts** (e.g. after a reboot/restore). Re-apply
the same two-line import + `context=_SSL` on each `urlopen` if the corpus starts throwing
`certificate has expired` again. The other pull scripts use `huggingface_hub` and are unaffected.

## Known remaining, not blocking

- **LTX-2.5 upscaler LoRA** (`Lightricks/...`, 0.33 GB): gated repo, was 403. Access requested on HF
  Sep 24; a later `CHAIN.ps1` pass grabs it once granted. Only gated repo in the whole plan.
- **Two corpus 404s:** `aviation.stackexchange` and `libretexts eng` ZIM filenames moved; need
  updated dates in `pull_corpus.py`. Unrelated to the cert fix.
- **`pull_research.py`** (extra, not in the manifest arithmetic): watcher runs it; watch disk if it's large.
- **Backup reserve:** manifest wants ~100-150 GB kept free for a restic backup — the highest-priority
  board item. Don't let the corpus fill the drive past that.

## When it finishes

Run `verify.py` (size-only is seconds; full sha256 ~3 h, resumable) BEFORE leaving the fast house.
"Already marked done" trusts marker files, not bytes, so verify is what actually proves the ~1.8 TB+
is intact. ZIM files and the two NIH sets publish no checksums, so their size check is the integrity check.
