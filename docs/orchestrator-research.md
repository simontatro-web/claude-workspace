# Jarvis orchestrator research: meeting every want (2026-09-25)

For Simon. Research and planning only: nothing here changes jarvis-1. Written in a Claude Code research session started 10:37 AM Central, Sep 25 2026, from the repo (HANDOFF, briefing Parts 4-5, benchmark results, 34 wiki pages) plus web research done in this session.

Companion files:
- `docs/orchestrator-roadmap.md`: the ordered build plan (safety first).
- `docs/orchestrator-wants-simon-2026-09-25.md`: your wants, verbatim. Quoted below as N1-N15 in the order you wrote them.
- Part 4 wants are W1-W24.

## Labels
- **MEASURED**: measured on jarvis-1 (source in the repo is named).
- **SOURCE**: read in code or docs; link given.
- **ESTIMATE**: arithmetic or judgment, not measured.
- **VERIFY**: unknown until a read-only check on the box; the exact command is in section 7.

## How to read this
1. Section 1: what exists today (ground truth).
2. Section 2: the one structure that every want hangs off. Read this first; most "how do I make sure X always happens" answers live there.
3. Section 3: your 15 new wants, one by one.
4. Section 4: the 24 Part 4 wants, mapped.
5. Section 5: conflicts between wants, and what cannot be done as asked.
6. Section 6: models and slots, with measured vs estimated numbers.
7. Section 7: VERIFY commands (all read-only).
8. Section 8: summary table.
9. Section 9: decisions you need to make.
10. Section 10: buy and download list.

---

## 1. Ground truth today (what the design starts from)

**Hardware and serving** (HANDOFF, Part 5)
- **Box:** 2x Xeon E5-2699 v3, 503 GiB RAM, 2x V100-PCIE-16GB, 990 PRO 1 TB (MEASURED).
- **Memory bandwidth:** STREAM Triad 29.5 GB/s on one socket, 59.5 GB/s on both (MEASURED).
- **Jarvis:** Qwen3.8-27B Q4_K_M on both GPUs, port 8080, `-c 24576 --parallel 2 --kv-unified`, MTP draft, reasoning "xhigh" (MEASURED ExecStart).
- **VRAM:** ~14.1-14.2 GiB idle per card, ~15.6 peak (MEASURED). No free GPU today.
- **Context truncation:** 4 silent `truncated = 1` events in 48 h, each one conversation filling the 24,576 window (MEASURED).

**Speed of the 27B, which decides the voice and front-desk plans.** Several older figures are on file:
- 28.09 t/s (layer split, no MTP)
- 83 t/s with MTP
- 69 t/s cited in agent-harnesses
- 29-52 t/s decode and ~630-650 t/s prefill on Sep 22, before p-min 0.4 and xhigh

Part 4 says re-measure before relying on any of them. **Now measured: see section 1a (decode ~45-58 t/s typical, prompt reading ~500-680 t/s).**

**Tool server** (port 8200, run as `simon`)
- Unrestricted `run_host_command`, plus write_file, read_file, save_finding, web_search, hf_model_sizes, create_tool (self-restart), list_tools.
- Bound to 0.0.0.0, so it is **exposed to your LAN** (MEASURED).
- Output capped at 4,000 characters.
- You chose the unrestricted shell on Sep 21 and full memory control on Sep 22 (jarvis-incidents, jarvis-run-host-commands).

**Pre-rebuild stack: gone** (MEASURED, Part 5)
- No job API, worker, ntfy notifier, healthcheck, supervisor, or embedding server.
- The Sep 14 design and code for all of them are documented in `docs/wiki/jarvis-orchestrator.md` and can be rebuilt quickly. They worked end to end on Sep 14 (MEASURED then).

**Backups:** none off-box (Part 4, HANDOFF). `~/jarvis-backup-stage/` is on the same drive and stale.

**Open WebUI** (port 3000)
- The system prompt is only 367 characters; safety sections 13/14/19 are missing (MEASURED, Part 5).
- Function Calling resets to "Default" on every new chat (documented gotcha, jarvis-orchestrator).

**Big models on the NVMe copy**
- GLM-5.3 (sha256-verified).
- Flash-Next UD-Q4_K_XL and GLM-5.3-Flash (copied, not yet hashed).
- ~62 GB free after these copies (HANDOFF).

**Model drive:** 4 TB USB, NTFS, mounted read-only, 2.7 TB used.
- Big models: MiMo-V2.6-Pro as two raw parts (must be joined, ~557 GB).
- Small models: router 1.7B, 2B distill, embeddings, rerankers, Qwen3Guard-4B, phi3.5 hallucination judge, Qwen3-VL-4B, OCR, ASR.
- Also corpus, data, audio/video/image models.
- Exactly which corpus and data sets finished downloading before the chain was stopped is VERIFY.

**Measured benchmark results so far** (docs/benchmarks)
- **GLM-5.3:** decode 0.9-1.1 t/s beside Jarvis, **1.48 t/s interleaved with Jarvis off**. At 16K context: 0.74 beside, 1.00 interleaved.
- **GLM-5.3 prefill:** ~10 t/s (512-token prompt), ~7.6 t/s (4096-token prompt), **~2.5-2.8 t/s at 16K depth** (all MEASURED).
- **Flash-Next, GLM-5.3-Flash, MiMo, and every small model:** nothing measured yet. Corrected Flash-Next estimates: ~5-6 t/s on socket 1 beside Jarvis, ~10 t/s interleaved with Jarvis off (ESTIMATE, docs/benchmarks/qwen3.8-flash-next.md).

What this means for every want below:
- The only fast, measured model is the 27B on the GPUs, and it has no spare VRAM.
- Everything big runs on the CPU at 1-10 t/s.
- The RAM rule is "Jarvis + ONE big model at a time" (HANDOFF).

---

## 1a. Verified on the box, 2026-09-25 10:57 AM Central (Simon ran `docs/orchestrator-verify.sh`)

Everything in this section is MEASURED from that run's output unless labelled otherwise. **Where it disagrees with the rest of this document, this section wins.**

### Speed of the production 27B, now measured
11 real requests on slot 1, 10:52-10:54 AM Central, today's config:
| | Range | Typical |
|---|---|---|
| Prompt reading | 343-722 t/s | ~500-680 t/s |
| Generation (decode, with MTP) | 42-79 t/s | ~45-58 t/s |
| MTP draft acceptance | 0.67-0.98 | mean draft length 3.9-5.9 |

**Why it matters:** those requests had 611-3,886 new prompt tokens each. At ~500 t/s, a 1,500-token prompt costs **~3 s before the first token, before any reasoning**. For the front desk and voice (N8, N10), prompt size and cache reuse matter as much as model speed. A ~300-token voice prompt should take ~0.6 s (ESTIMATE from these rates).

### Reasoning can be turned off per request
The chat template (V10) reads `enable_thinking` and `reasoning_effort`:
- Reasoning is applied only if `enable_thinking` is undefined or true.
- The allowed efforts are xhigh (the default), medium and low.

So the voice and front-desk presets can send `chat_template_kwargs: {"enable_thinking": false}` (or `"reasoning_effort": "low"`) per request with no server change. Whether a per-request value overrides the server's `--chat-template-kwargs` default is **VERIFY**: V23 below is a one-request test.

### Exposure and permissions: worse than assumed in two places
- **Firewall:**
  - ufw is inactive and the INPUT policy is accept.
  - **8080 (llama-server, no API key), 3000 (Open WebUI), 8200 (the unrestricted shell) and 111 (rpcbind) all listen on every interface.**
  - Tailscale serve has no config.
- **Group memberships:**
  - `simon` is in `sudo` (password required; no NOPASSWD entries). The Sep 14 note that `sudo -n nvme smart-log` works was from the old box and **no longer holds**.
  - `simon` is **not** in `docker`.
  - **`simon` IS in `lxd`.** If LXD is installed, membership in `lxd` is effectively root without a password: a member can start a privileged container with the host's `/` mounted. Jarvis runs as `simon`, so its "unrestricted shell" may have a password-free path to root. **VERIFY V24** (is LXD installed and its socket present). If it is, removing `simon` from `lxd`, or at least keeping the future `jarvis` user out of it, belongs in roadmap step 1.6.
- **Production 27B:** runs as `User=simon` with `OOMScoreAdjust=0` and `MemoryMax=infinity`.
  - Any process running as `simon`, including Jarvis's shell, can kill it by PID with no sudo. That is exactly how the pkill incidents worked.
  - A big-model load that exhausts RAM is as likely to OOM-kill Jarvis as the experiment. The benchmark units protect themselves with `OOMScoreAdjust=1000`, so the risk is lower for them, but anything launched without that pattern is not protected.
- **Tool server:** `User=simon`, `--host 0.0.0.0`, key in an EnvironmentFile (mode 600). As expected.

### Disk, memory, links
- **NVMe:** 915G, **807G used (93%), 62G free**. `/mnt/models`: 2.7T used, 1.1T free.
- **RAM:** 492 GiB available at the time of the check. There is a 7 GiB swap file. Benchmark units disable swap for themselves; production does not.
- **NVMe link:** 8 GT/s x4 (the drive is capable of 16 GT/s, and the PCIe 3.0 board downgrades it), so **~3.9 GB/s max**. The "~2-3 min to load GLM-5.3 from NVMe" estimate stands, plus repack time.
- **Model drive:** on USB 3.0 (5000M) with the UAS driver. Its HDD speed, not USB, is the limit (the ~35-60 min estimates for big loads stand; ESTIMATE).
- **GLM-5.3 load time:** no glm-test journal lines (V20). Still unmeasured.

### Update exposure
- `apt-mark showhold` is **empty**: the NVIDIA driver is not held.
- The running kernel is 6.8.0-142, and the NVIDIA 580.178.04 DKMS module is built for both 6.8.0-139 and -142. So **a kernel update has already happened and DKMS rebuilt the driver correctly**. That lowers the risk of kernel updates; it does not remove the risk of a driver-package update.
- unattended-upgrades allows the security pockets and has an **empty Package-Blacklist**. Whether the 580 driver packages come from a pocket unattended-upgrades would touch is VERIFY (V25).

### Tailscale naming
- This box is **`jarvis-2` (100.101.72.69)** on the tailnet.
- `jarvis-1` (100.87.7.19, offline 4 days) and `jarvis` (offline 14 days) are old entries. The wiki's `jarvis-1.tail7b6a92.ts.net` URLs are stale.
- Your iPhone 14 is on the tailnet, which confirms phone approvals over Tailscale are possible.

### Components that DO exist on the model drive (downloads avoided)
| Directory | Contents |
|---|---|
| `verify/` | HHEM-2.1-open, prompt-injection-deberta, Qwen3Guard-Gen-4B, Qwen3-VL-4B, phi3.5 hallucination judge, docling-models |
| `audio/` | Kokoro-82M-ONNX, Kokoro-82M GGUF (q8_0, audio.cpp), faster-whisper large-v3 and large-v3-turbo, whisper.cpp |
| `embed/` | Qwen3-Embedding-4B, Qwen3-Reranker-4B, Qwen3-VL-Reranker-2B, jina-code |
| `slots/` | router-Qwen3-1.7B, router-alt-2B-distill, asr, embedding, ocr, reranker |
| `data/research/` | RAGTruth, SimpleQA, SimpleQA-verified |

The groundedness gate, the injection filter, text-to-speech, speech-to-text, the router and the calibration sets are all already on the drive.

### Offline corpora present
Wikipedia (maxi 2026-08 at 127 GB, and nopic 2026-06), Stack Overflow plus ~25 Stack Exchange sites, LibreTexts (bio, chem, math, phys, med, k12), mdwiki, WikEm, Wikibooks, Wikiversity, Wikispecies, Gutenberg, iFixit, CrashCourse, the World Factbook.

**Not seen: PMC and PubMed.** They are not in the corpus listing (maybe under `corpus/refs/` or never downloaded; VERIFY V26). So the research spec's "local PMC/PubMed first" plan is not available yet. Wikipedia, the Stack Exchange sites and LibreTexts are.

**Integrity flags**
- `gardenology.org_en_all_2026-09.zim` is exactly 33,554,432 bytes (32 MiB, a power of two): almost certainly a **truncated download**.
- `gardenology`, `zimgit-medicine` and `wikipedia_en_all_maxi` all have the same 22:32 timestamp, when the chain stopped. **Check the Wikipedia maxi file's size against the published size before trusting it** (V26).

### Things that are gone
- **No browser stack** (V16): the headed Chrome / Xvfb / CDP bridge from Sep 14 did not survive the rebuild. Website review (N13) and research page-reading (N6) need a browser again: Playwright's Chromium, headless, under the `jarvis` user.
- **No `/metrics`** on llama-server (501; needs `--metrics`). `/slots` works (200), so the control room can read slot state today.

### Open WebUI
- Image `ghcr.io/open-webui/open-webui:main`, created 2026-09-21.
- `main` is a moving tag, so a future `docker pull` can silently change versions. Pin a release tag at the next deliberate recreate (with `~/recreate-webui.sh` or its successor).

### Backup tooling
- restic 0.16.4 is installed.
- `~/.config/jarvis/restic-pass` exists (mode 600). **Keep a copy of that password off the box**, or the backup cannot be restored after a dead NVMe.
- No repository location is known yet (D3).

### Follow-up checks (all read-only, or a single harmless model request)
| # | Settles | Command |
|---|---|---|
| V23 | Per-request thinking-off works against the server default | `curl -s -m 60 http://127.0.0.1:8080/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"Say OK."}],"max_tokens":40,"chat_template_kwargs":{"enable_thinking":false}}' \| python3 -c "import json,sys; m=json.load(sys.stdin)['choices'][0]['message']; print('reasoning chars:', len(m.get('reasoning_content') or '')); print('content:', m.get('content'))"` |
| V24 | Is `lxd` membership a live root path | `snap list 2>/dev/null \| grep -i lxd; ls -l /var/snap/lxd/common/lxd/unix.socket 2>&1; command -v lxc` |
| V25 | Where the NVIDIA driver packages come from | `dpkg -l \| grep -E '^ii +(nvidia-driver\|nvidia-dkms\|libnvidia-compute)' \| head; apt-cache policy nvidia-driver-580 2>/dev/null \| head -12` |
| V26 | PMC/PubMed presence; ZIM integrity; model folders complete | `ls -la /mnt/models/models/corpus/refs /mnt/models/models/corpus/ted /mnt/models/models/data/research 2>&1 \| head -60; ls -la /mnt/models/models/verify/HHEM-2.1-open /mnt/models/models/verify/prompt-injection-deberta 2>&1 \| head -40` |


## 2. The spine: one structure that makes the wants enforceable

Your wants keep using "100%", "every time", "never". A model cannot promise any of those, however it is prompted: this box has proof. The pkill rule was in the operating manual, and the production server was still killed three times in one day (jarvis-incidents). So each "must" below lives in **code, database constraints, and Linux permissions**, and the model is a component inside that. This is the governing idea from Part 4 ("SQLite holds truth, workers act on schedules, the model reads and phrases"), made concrete.

### 2.1 Four Linux users (the fence everything else depends on)

| User | Runs | Can write | Cannot touch |
|---|---|---|---|
| `simon` | You. Production units are root-owned. | everything via sudo | n/a |
| `jarvis` (new) | The tool server, Jarvis's shell, create_tool plugins, build sandboxes | its own home (`/home/jarvis`, incl. its memory dir, where it keeps full control as you chose), job workspaces | `/etc`, systemd units, `/home/simon`, the job DB, approvals, backups, the scorer, `~/.config/jarvis` secrets |
| `jarvis-core` (new) | Job API, queue worker, approvals API, event log, notifier | `/srv/jarvis/db/jarvis.db` (mode 600) | anything else |
| `jarvis-eval` (new) | The scorer: eval harness and held-out test sets | its own results dir | nothing in the harness code, which is root-owned. `jarvis` can read the public half and none of the held-out half. |

**Why this is the key step.** Today Jarvis's shell runs as `simon`. So any rule stored in a file or database `simon` can write is a rule Jarvis can rewrite, including "no job runs without an approved spec". With the four users:
- Jarvis keeps an **unrestricted shell as `jarvis`**, which honours your Sep 21 choice.
- Jarvis keeps **full control of its memory** (it lives in `/home/jarvis`), which honours your Sep 22 choice.
- Jarvis **structurally cannot** approve its own spec, edit its scorer, stop production, or delete backups.

This is the "maybe behind sudo access" idea from your wants, done precisely. Jarvis gets no sudo at all. You keep sudo. A polkit rule lets `jarvis` start and stop only units named `jarvis-sandbox-*`; the standard pattern is `action.id == "org.freedesktop.systemd1.manage-units"` plus a unit allow-list (SOURCE: [ArchWiki polkit](https://wiki.archlinux.org/title/Polkit), [Baeldung example](https://www.baeldung.com/linux/systemd-service-restart-specific-user)).

### 2.2 The state: one SQLite database owned by `jarvis-core`
Tables (extends the Sep 14 schema that already worked: jobs/deadlines/findings/runs/approvals):
- **Specs**
  - `specs`: id, title, job_type, status (draft / proposed / approved / superseded), body_md, content_sha256, approved_sha256, approved_at, approved_via.
  - `spec_turns`: every interview question and answer, saved as it happens, so an interview survives the 24,576-token context limit and a new chat.
- **Jobs**
  - `jobs`: id, spec_id (NOT NULL for build/research types), type, status, slot, caps (max wall clock, max tokens, max iterations), parent_job.
  - `steps`: every model call a job makes: model, slot, prompt tokens, output tokens, wall time, outcome.
- **Visibility**
  - `events`: an append-only log of everything that happens: "prompt routed to glm53 (reason: hard review, confidence 0.91)", "model load started", "job 12 step 3 failed tests". This one table feeds the control room (N12), the front desk (N8), the daily audit (W20) and the weekly retrospective.
- **Approvals and grounding**
  - `approvals`: pending actions (spec approval, suggestion, email send, model download, promotion to production). Approve or deny from your phone.
  - `claims`: research and review claims, each with its source, verbatim quote and gate verdict (for N6, N15).
- **Models**
  - `models`: every model file, where it lives (NVMe / drive), RAM and VRAM cost, measured speeds, verified hash. The router and the admission controller read this table.

### 2.3 The gate that makes the spec interview mandatory (N1)
Enforced in three places, so no single failure lets a job through:
1. **Schema.** A build or research job cannot be inserted without a spec_id: a CHECK constraint or trigger.
2. **Claim check.** The worker claims a job only if `specs.status = 'approved'` AND `specs.approved_sha256 = sha256(body_md)`. So a spec edited after approval is automatically unapproved.
3. **Approval path.** Approval is written only by the approvals API, and only with your credential (the phone button or the control-room page). The model's tools have no "approve" call. Even through its shell, `jarvis` cannot write the database (section 2.1).

Result: "never queue a build until fully specced and approved by me" is a property of the system, not a promise from the model. How good the interview is (whether the model really understands) is a separate problem: see N1.

### 2.4 The model manager (N3, N4)
- **Production 27B:** stays exactly as it is, its own root-owned unit on 8080. Nothing can stop it except you.
- **Every other model:** runs behind **llama-swap**, a small proxy that starts the right llama-server on demand, unloads on a TTL (time-to-live after last use), and exposes running models plus load/unload over HTTP. MIT licence, ~5.8k stars; it has a `/ui` with live request logs and manual load/unload (SOURCE: [github.com/mostlygeek/llama-swap](https://github.com/mostlygeek/llama-swap)).
- **Why llama-swap, not llama.cpp's own router mode (`--models-preset`, `--models-max`)** ([server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)): each llama-swap model's `cmd` is an arbitrary command. So it can launch through the patterns you already proved on this box:
  - `systemd-run` with `MemoryMax`, `OOMScoreAdjust=1000` and no swap
  - `numactl` placement
  - `-lm dio`
  - a fork binary (GLM-5.3-Flash needs Unsloth's fork; Flash-Next MTP needs the PR build)

  Router mode runs one llama-server binary and gives you no such wrapper. VERIFY whether router mode passes per-model binary paths. The docs read in this session do not say.
- **Admission controller** (your code, ~100 lines): before any load, it checks the `models` table against live `free`/`nvidia-smi` and enforces:
  - Jarvis + one big CPU model.
  - GLM-5.3 and MiMo are exclusive.
  - No GPU render during a two-card LLM load (power rule, what-not-to-do #21).
  - MiMo requires Jarvis stopped, and therefore your approval.

  A refused load becomes an event and a phone message, never a crash.

### 2.5 Grounding gates (N13, N15, W3)
Every review or answer that claims a fact passes something that is not a language model's opinion:
- **Code:** tests actually run.
- **Websites:** a page load in the headed Chrome, console errors, DOM assertions, screenshots.
- **Research:** a re-fetch of the source plus a string match of the quote.
- **Groundedness:** a small checker scores every sentence against its source: HHEM-2.1-Open or MiniCheck. The status of both, and whether they are on your drive, is in N15.
- **Status answers:** read from the database, never from model memory.

### 2.6 Notifications and approvals from your phone (N13, GAP 2)
Recommended: self-host **ntfy** on the box, tailnet-only, with `auth-default-access: deny-all`. For instant iOS delivery, set `upstream-base-url: https://ntfy.sh`. Only the message ID and a SHA-256 of the topic URL go to ntfy.sh; message text never leaves your box (SOURCE: [ntfy config docs](https://raw.githubusercontent.com/binwiederhier/ntfy/main/docs/config.md)).
- **How an approval works:** a notification carries Approve and Deny action buttons. Each button is an HTTP POST from your phone, over Tailscale, to the approvals API. The POST carries a one-time token tied to that approval row, so a leaked topic cannot approve anything.
- **Known iOS bug:** the ntfy iOS app does not honour `clear: true` for http actions, so an approval notification stays on screen after you tap it (SOURCE: [ntfy issue #1728](https://github.com/binwiederhier/ntfy/issues/1728)). Workaround: the approvals API sends a follow-up "Approved ✓" message. Fallback app: Pushover (one-time $5, VERIFY price).
- **Anything bigger than yes/no** (deny with a reason, "change X") goes to a small approvals page in the control room, opened from the notification's view action.

### 2.7 The kill switch (ADD 1)
- **What:** one systemd target, `jarvis-autonomy.target`. Every autonomous unit (worker, scheduler, research, RSI, llama-swap slots) is `PartOf=` it. `systemctl stop jarvis-autonomy.target` stops all of them at once. Production 27B, Open WebUI, and the health watchdog are NOT part of it, so you never lose the chat or the alarms.
- **Belt and braces:** a pause flag (a row in the `jarvis-core` database) that every worker checks before claiming work.
- **From your phone:** a pinned ntfy "PAUSE ALL" action, plus a button in the control room. Both need your credential. `jarvis` cannot un-pause itself.

---

## 3. Your 15 new wants, one by one

### N1. The spec interview, every time, before anything is queued ("I WANT THE MIDDLE MAN MODEL TO 100% do this everytime")

**Have**
- A tested pattern from the research spec (`deep-research-optimization`, "THE SCOPING INTERVIEW"): the output is a contract, and "what would change the answer" is the single best question.
- The approvals table design from Sep 14 (jarvis-orchestrator, MEASURED working then).
- The 27B on the GPUs, the only model fast enough to hold a conversation.
- A role test already defined in `docs/benchmark-campaign.md` ("Spec interviewer"). Not run yet.

**Missing**
- The gate (section 2.3).
- The interview flow itself.
- The restatement check.
- A way to test that the spec really carries your vision.

**How it should work**
1. **The gate:** section 2.3. This part can be made truly 100%: the worker will not claim a build or research job without your approved, unmodified spec. Tested by trying to enqueue an unapproved job (refused) and by trying to write the database as `jarvis` (permission denied).
2. **The interview is driven by a checklist per job type, not by the model's mood.**
   - Each job type (website, app, tool, research, self-change, purchase research) has a checklist stored in the database.
   - Website example: purpose; who uses it; pages and features; data it keeps; look and feel; where it runs; what "done" means as checkable tests; what is out of scope; budget and deadline; "what would make you say it's wrong".
   - The model may not propose the spec while any item is empty. You can answer "you decide" for an item; it is then recorded as an **assumption** you approve later.
   - Tiny jobs (a timer app) get a short checklist but still go through the gate, as you asked.
   - The interviewer asks one or two questions at a time and saves each answer into `spec_turns` straight away ("saving it to memory along the way"). A chat that dies or truncates loses nothing.
3. **The restatement must be the model's own picture, and code checks that.** When proposing, the model must fill fixed sections:
   - (a) a walkthrough of the finished thing from your point of view ("you open it, you see...");
   - (b) things it inferred that you never said, each marked as an inference;
   - (c) assumptions and defaults it chose;
   - (d) acceptance tests: concrete, checkable, each one pass or fail;
   - (e) out of scope;
   - (f) risks and open questions.

   A mechanical check rejects an echo before you ever see it:
   - word n-gram overlap with your own interview answers above a threshold (e.g. >50% of 4-grams copied; to be tuned against real interviews): ESTIMATE threshold;
   - fewer than N inferences;
   - any acceptance test that is not checkable.

   You approve, or edit and approve. The approval stores the hash.
4. **"Does it really understand?": test it, don't trust it.** After you approve, a **fresh** model instance that sees only the spec (not the chat) answers an automatic quiz generated from your interview answers ("what happens when a student gets a question wrong?"). Wrong answers mean the spec document does not carry your vision, and the gap goes back to you before the build starts. This is also exactly your later idea of quizzing the big reviewer model (N13). It matters because every downstream model gets only the spec, never the chat.

**Which model**
- The 27B (only interactive-speed model; decode speed on the current config is VERIFY).
- An optional overnight "spec critic" pass by a bigger model (GLM-5.3 measured 1.0-1.5 t/s) adds any missing questions to your morning list without slowing the conversation.
- How well the 27B asks questions is **not measured**. Run the "spec interviewer" role test in benchmark-campaign.md before trusting it: 10 vague requests, each with a hidden checklist, scored on coverage.

**Risks and honest limits**
- The gate is 100%. The *understanding* is not and cannot be; it is measured by the quiz and your approval. A model can pass an overlap check and still be wrong about what you meant.
- Fatigue: for every tiny task, a full interview will get annoying. The checklist-size-per-type design is the pressure valve. You can also set a type as "express" (3 questions), which still needs your approval.
- **Context:** the 24,576 window and xhigh reasoning fill fast. Long interviews must live in the database, not the chat (hence `spec_turns`).
- **Open WebUI cannot enforce a flow.** The interview runs either as an Open WebUI "pipe" function that talks to the job API, or on its own page. The tools the model gets are `spec_draft_update`, `spec_propose`, `spec_status`. There is no `spec_approve`.

### N2. Jarvis builds and improves itself ("Make this UI ... route certain tasks to certain models")

**Have**
- create_tool, write_file, self-restart, and a proven "Claude writes the spec, Jarvis writes the code" pattern: the 124-line browser agent written first try, Sep 12 (jarvis-system-build W4).
- GVS5H already proven on this box for coding (MEASURED Sep 14: job 25 done end to end, 27 min, 7 calls).

**Missing**
- Self-changes going through the same gate as everything else.
- A staging area.
- A promotion step.
- A scorer.

**How it should work.** A self-change is just a job with `type = self_change`:
1. Spec interview (N1).
2. The build happens in a **sandbox**: a git branch in a job workspace owned by `jarvis`, run under `jarvis-sandbox-<job>` units or rootless containers, on test ports. Never on 8080, 3000, or the tool server's live port.
3. Tests and the scorer run as `jarvis-eval` (section 2.1).
4. Promotion to live is a separate approval from your phone, showing the diff summary and the test results.
5. Promotion is done by `jarvis-core` with a pre-promotion backup, so undo is one command.

create_tool stays, but plugins load into the `jarvis` tool server only. They cannot touch production, because the tool server runs as `jarvis`.

**Which model**
- The 27B orchestrates, with GVS5H-style decomposition. GVS5H claims 69.2 → 92.4% on LiveCodeBench-hard for this exact 27B (SOURCE: [GVS5H README](https://github.com/slee-persis/GVS5H), via agent-harnesses). Not reproduced on this box.
- AA shows the 27B at **6% on Terminal-Bench** (model-benchmark-dataset, SOURCE: AA). It is weak as a free-roaming shell agent, which is another reason builds should be tests-driven steps, not open shell sessions.
- Flash-Next and GLM take the hard pieces (N3).

**Risks**
- Self-modification plus an unrestricted shell is exactly the setup behind the pkill incidents and the runaway GGUF-parser loop. Everything in this want depends on section 2.1 existing first.
- Every job needs hard iteration and wall-clock caps, in code (jarvis-incidents, Sep 21 evening).

### N3. Routing jobs to big models with fresh context each time

**Your idea is right, and the measurements back it.**
- GLM-5.3 decode falls as context grows: 1.106 → 0.928 → 0.74 t/s at depth 0 / 4K / 16K beside Jarvis.
- Prefill falls far faster: ~10 t/s empty → ~2.5 t/s at 16K (MEASURED, docs/benchmarks/glm-5.3.md).
- So "one task, full spec, new chat, then close it" is the correct way to use the big models. It is also the pattern research found works best, the verification-subagent / ledger pattern: fresh instances get the spec plus artifacts, not the history (deep-research-optimization, agent-harnesses).

**What a single big-model call costs** (ESTIMATE from measured GLM rates)
- An 8,000-token brief (spec + relevant files) at ~4-7 t/s prefill: **~20-35 min before the first output token**.
- 5,000 output tokens including reasoning at ~0.85-1.4 t/s: **~1-1.6 h**.
- So **~1.5-2.5 h per GLM-5.3 call**. A build of ten such steps is a night or more.
- GLM-5.3 is therefore a **single-shot** model: one well-specified hard piece, a design, or a final review. It is never an agent in a multi-turn tool loop.
- **Flash-Next** is the realistic big "worker": ~5-10 t/s estimated, prefill **not measured**. That number decides how much of the building it can take.

**How it should work**
- The job worker (code) prepares the brief: the spec, the acceptance tests, only the files the step needs, and a required output format (a patch, a file, a JSON verdict).
- It calls the big model through llama-swap in a new request with no history, stores the output as an artifact, runs the tests, and records the step.
- "Incorporating what they built" is done by the worker plus tests plus the reviewer (N13), and promotion needs your approval. The small model never "pastes it in" unchecked.
- Prompt caching: every call starts fresh, so cross-call caching barely matters. The one exception is a fixed system prefix for GLM. GLM's dense MLA cache is the low-risk kind for reuse (context-and-speed-per-model). VERIFY with `-lv 4`.

**Which model**
- Default worker: Flash-Next (unmeasured).
- Hard single shots and final reviews: GLM-5.3 (measured 1.0-1.5 t/s decode).
- GLM-5.3-Flash as a possibly faster middle rung: unmeasured, and it needs the Unsloth fork build.
- MiMo only as an event: N4.

**Risks**
- Throughput: the queue will hold hours of big-model work per job. The ETA shown must come from `runs` medians, not guesses.
- RAM: Flash-Next (~104 GiB) and GLM-5.3 (~430 GiB) cannot both be resident next to Jarvis. The admission controller unloads one first.

### N4. Route to any model, including loading MiMo from the HDD; use every resource; ask me when something is missing

**Have**
- Every model file (drive plus NVMe), the RAM rule, `-lm dio` direct loading (MEASURED working for GLM).
- The `systemd-run` launch pattern with memory caps (MEASURED).
- hf_model_sizes.

**Missing**
- llama-swap plus the admission controller (section 2.4).
- The `models` table.
- A "missing resource" request type.

**How it should work**
- The router asks "which slot?" and the admission controller asks "can it load now, and what has to unload?".
- If a model is on the drive but not on the NVMe, the controller either:
  - loads straight from the drive (read-only mount; USB read speed limits it), or
  - queues a copy job (rsync plus sha256 verify, as done for GLM) for your approval.
- If the resource does not exist (a model, a package, disk space), Jarvis files a `resource_request` approval saying what, why, size and where. You approve a download, or add it to the fast-house batch list.

**Load times** (ESTIMATE; measured load times are not on file, VERIFY)
- From the USB HDD (~150-250 MB/s for a 4 TB CMR disk; USB 3.0 allows more):
  - GLM-5.3 at 468 GB: **~35-50 min**
  - MiMo at 557 GB: **~40-60 min**
- From the 990 PRO: this board's PCIe 3.0 x4 caps it near ~3.5 GB/s, so **~2-3 min for GLM-5.3**, plus CPU repacking time at load.

**MiMo specifically: this cannot work the way you pictured it**
1. It is two raw parts and **must be joined into one file first** (~557 GB). llama.cpp cannot load the raw parts. There is no room on the NVMe today (~62 GB free). The join needs either:
   - a new 2 TB drive (section 10), or
   - removing the GLM-5.3 NVMe copy (the drive keeps the original) and more; tight even then (ESTIMATE: 55 base + 128 Flash-Next + 188 GLM-Flash + 519 MiMo ≈ 890 GiB of ~915 usable).
2. It fits only with the experts in RAM (~466 GiB) and ~30 GiB of other tensors on **both** GPUs, which means **the 27B must be stopped** (mimo-v2.6-feasibility, SOURCE; unmeasured on this box).
3. So "Jarvis loads MiMo" means **Jarvis turns itself off** for the whole MiMo session. With ~14 GiB of RAM left, a tiny CPU "night receptionist" (the 1.7B router model) could still answer status questions from the database during the run: ESTIMATE, unmeasured.

This makes MiMo a scheduled, approved event (night window, like the benchmark runner's 1-7 AM rule), never an automatic routing target. Expected speed ~2-5 t/s (ESTIMATE, SOURCE: wiki), prefill unmeasured.

**Risks**
- Automatic loading is exactly what can starve production RAM. The admission controller must never unload or stop the production 27B. That is enforced by the 27B's unit being root-owned and outside llama-swap, not by a rule.
- Jarvis downloading by itself uses the NVMe's scarce free space and your home bandwidth. Default: Jarvis writes the download manifest; you or the fast house pulls it.

### N5. An always-on self-improvement (RSI) loop: intelligence, speed, capability

**Have**
- The plan in Part 4 (the scorer it cannot tamper with, GEPA first, DGM-style code changes later, no training on its own outputs).
- The benchmark tooling (bench.sh, queue-runner.sh) with night windows.
- create_tool.

**Missing**
- The unwritable scorer.
- The held-out set.
- Version lineage.
- Caps.
- An optimizer.

**Options found**
- **GEPA** for prompts and other text components.
  - Reflective evolution with a Pareto frontier.
  - Claims 100-500 evaluations where RL needs 5,000-25,000+.
  - Works with local models through LiteLLM `api_base`, has an `optimize_anything` API with a custom evaluator.
  - MIT, ~6.7k stars (SOURCE: [github.com/gepa-ai/gepa](https://github.com/gepa-ai/gepa)).
- **OpenEvolve** (open AlphaEvolve) for code with an evaluator.
  - Any OpenAI-compatible API, checkpointing, Apache-2.0, ~7.4k stars.
  - Its docs describe **no sandbox for the evaluated code** (SOURCE: [github.com/algorithmicsuperintelligence/openevolve](https://github.com/algorithmicsuperintelligence/openevolve)), so it must run inside the `jarvis-sandbox` fence.
- **Self-Harness** (edits the harness, keeps weights and evaluator fixed): the method to copy (agent-harnesses, SOURCE: arXiv 2606.09498).
- **Scorer tooling**:
  - promptfoo for prompt-regression suites (in the local-eval-harness wiki page);
  - lm-evaluation-harness `--model gguf` for anchors;
  - `llama-perplexity --kl-divergence` for quant and flag quality (local-eval-harness, SOURCE there).

**How it should work, honestly scoped**
- **What "improve itself" can really mean here, in order of safety:**
  1. prompts, routing thresholds, checklists;
  2. llama-server flags, only through the benchmark queue with A/B and your approval to promote;
  3. tool and harness code in the sandbox, scored by `jarvis-eval`;
  4. LoRA adapters for style (W6).
- **What it cannot mean:** raising the models' own intelligence. Training on its own outputs is not viable (Part 4), and the weights are fixed. Put plainly: this is continuous, measured tuning of the scaffolding around fixed models, not an intelligence explosion. Scaffolding still matters a lot: GVS5H's +23 points came from scaffolding alone.
- **The loop:** propose a change, run it in the sandbox, `jarvis-eval` scores it on the public set and then the held-out set, and it is archived either way. If both sets improve and nothing regresses: a promotion approval goes to your phone. Caps per night: iterations, wall clock, tokens. A no-progress detector stops it. The kill switch covers it.
- **Always on vs your chat:** the loop is a batch job at the lowest priority. It gets the GPU 27B only through the batch semaphore (one slot always free for you), and the CPU big models mainly at night.
- **Start order:** the loop's first job is not optimisation. It is proving the scorer catches a planted regression (Part 4: "Code self-modification only after the scorer has caught a real regression").

**Risks**
- The documented failure from the literature: Darwin Gödel Machine runs **faked test logs and removed detectors**, even with the detectors hidden (Part 4, jarvis-progress). That is why the scorer must be unwritable, not merely hidden (section 2.1).
- Held-out leakage: if `jarvis` can read the held-out tests, scores become meaningless. They live mode 700 under `jarvis-eval`.
- **Conflicts with N14 ("never break") by nature.** It is only compatible because promotion needs your approval and the production units are out of its reach.

### N6. Deep research all night ("research what hardware I could buy that would improve you")

**Have**
- A full spec already written: `D:\models\RESEARCH-SPEC.md`, summarised in `deep-research-optimization` (scoping interview → query matrix → crawl with saturation stopping → per-claim table with verbatim quotes → gate → one synthesis pass → adversarial review → report with a "what I could not establish" section).
- Jarvis's `web_search` (DuckDuckGo scraping) and `save_finding` tools.
- The headed Chrome/CDP stack if it survived the rebuild (VERIFY; Part 5 lists no browser service).
- Research downloads that may be on the drive: rerankers, embeddings, SimpleQA/FRAMES/RAGTruth datasets, corpora (PMC, PubMed, Wikipedia ZIMs). Which ones landed is VERIFY.

**Options found**
- **local-deep-research**: MIT, ~9.1k stars.
  - Speaks llama.cpp's OpenAI endpoint at `localhost:8080/v1` directly.
  - Engines: arXiv, PubMed, Semantic Scholar, Wikipedia, SearXNG, GitHub, Wayback, Google, Brave.
  - Claims ~95.7% SimpleQA with the previous-generation 27B on one 3090.
  - Its own run times are 1-5 min (quick) to 10-30 min (full report) (SOURCE: [github.com/LearningCircuit/local-deep-research](https://github.com/LearningCircuit/local-deep-research)).
  - SimpleQA is short factoid questions, not multi-source synthesis; that number is not "research accuracy" (deep-research-optimization).
- **Search APIs, as of this session:**
  - **Tavily:** 1,000 credits/month free, no card; $0.008/credit after (SOURCE: [Tavily pricing](https://help.tavily.com/articles/8816424538-pricing)).
  - **Serper:** 2,500 free credits (valid 6 months), then ~$1 per 1,000 down to $0.30 (SOURCE: [serper.dev](https://serper.dev/)).
  - **Brave:** free tier removed Feb 2026. Now $5/month in credits (~1,000 queries), a card on file is billed beyond that, and attribution is required (SOURCE: [implicator.ai report](https://www.implicator.ai/brave-drops-free-search-api-tier-puts-all-developers-on-metered-billing/)).
  - **SearXNG:** its maintainers report Google down, Bing irrelevant, DuckDuckGo CAPTCHAs (Jan 2026; deep-research-optimization). **Do not build on it.**

**How it should work**
- Research is a job type behind the N1 gate. Scoping is the interview, and "what would change the answer" is mandatory.
- The worker runs the crawl:
  - frontier table, dedupe, a checkpoint per document, a hard budget in code, novelty-rate saturation as the stopping rule;
  - claims stored with a verbatim quote;
  - claims gated by the groundedness checker;
  - a sample re-fetched and string-matched;
  - numbers never paraphrased;
  - one synthesis pass, then a review by a different model family.
- Output: a document in the repo or memory, plus the claim table. In the morning you get a notification with counts (documents read, claims kept, claims dropped) and the "could not establish" list.
- For your example ("hardware that would improve you"), the brief must carry the box facts so the research is about *this* box:
  - Haswell AVX2, DDR4 at 1866, PCIe 3.0;
  - V100 is the last CUDA/driver generation;
  - the 240 V circuit question.

  The wiki already holds a lot of this: the E5-2699 v4 swap at ~$150-240 for the pair (SOURCE: system-performance-levers; price VERIFY), the 1 TB RAM path, gpu-upgrade-options.

**Throughput** (ESTIMATE)
- The research spec estimates ~1,600 documents per 8-hour night single-stream at the old 145 t/s prefill; 2,000-3,000 with batching.
- If the Sep 22 ~630 t/s prefill still holds on the current config (VERIFY), the 27B could read several thousand extracted pages a night. That uses the GPU slot you chat on, so reading runs at night and in batch.
- Flash-Next prefill is unmeasured; it decides whether reading moves to the CPU.
- Search volume: a deep night of 200-500 queries. Tavily free plus Brave credits (~2,000/month together) covers roughly 4-8 deep nights a month. Serper at ~$1/1K covers the rest, well inside $25.

**Which model**
- Triage: the 1.7B router with grammar-forced labels (unmeasured).
- Read and extract: the 27B at night, or Flash-Next (unmeasured).
- Synthesis: GLM-5.3 once per night (measured 1.0-1.5 t/s; ~2-4 h for one synthesis over a 10-15K-token claim table, ESTIMATE).
- Review: the other family.

**Limits, plainly**
- A local model cannot self-verify to your 95% bar on synthesis. AA-Omniscience penalises confident wrong answers, and local scores are negative: the 27B and Flash-Next both −10, against Claude Opus 5 +37 (model-benchmark-dataset, SOURCE: AA).
- The design makes research auditable and flagged, not frontier-accurate.
- The cheap fix for the conclusion: one frontier call that audits the synthesis against the claim table (the top escalation step, W9, within budget).

### N7. Build any tool, e.g. a YouTube finder that returns only videos that fix what I keep getting wrong

**Have**
- The learning protocol (Part 4: only vetted, on-topic videos; random videos are harmful for you).
- The ACT knowledge pack and generator (jarvis-act-generator).
- The rule "diagnose from real graded work, not generated quizzes": a generated ACT diagnostic correlated only 0.26 with real results (W8).

**Missing**
- A learner model (a `skills` table).
- YouTube access.
- Transcript grounding.

**Options found**
- **YouTube Data API v3:** free, 10,000 units/day. `search.list` costs 100 units. Since June 2026 search is its own budget of **100 search calls/day** (SOURCE: [Google quota docs](https://developers.google.com/youtube/v3/determine_quota_cost), [socialcrawl summary](https://www.socialcrawl.dev/blog/youtube-data-api-2026)). Plenty for tutoring use.
- **Transcripts:** `youtube-transcript-api` or `yt-dlp --write-subs`. Both are unofficial and can break when YouTube changes things. A home IP is usually fine where cloud IPs get blocked (ESTIMATE, VERIFY on the box).

**How it should work, and why "accurate" is achievable here**
1. **What you struggle with comes from data, not vibes.** A `skills` table fed by real graded work (you paste or upload it; nothing is ever submitted) and by tutoring-session mistakes. Each row carries its source (W8 rule). The finder's input is a specific misconception ("sets up related-rates with the wrong derivative variable"), not a topic name.
2. Generate 5-10 queries. Search with filters: duration, recency, a channel allow-list you approve once (Khan Academy, The Organic Chemistry Tutor, Professor Leonard, 3Blue1Brown, and whatever you add).
3. **Ground on the transcript, not the title.** Fetch the transcripts and chunk them. A reranker scores each chunk against the misconception text. A video qualifies only if some window actually explains that exact point. The result names the timestamp.
4. The 27B reads only the top windows against a checklist (correct? at your level? addresses the misconception?). It returns 1-3 videos with timestamps and a one-line reason each, or "none good enough".
5. Your thumbs-up or thumbs-down is stored and adjusts the allow-list and ranking.

**"Build any tool" in general** = N2's pipeline: spec, sandbox, tests, approval, promotion. The limit is not the model. It is (a) accounts and quotas you must set up, and (b) things that need judgment with no ground truth.

### N8. A fast front-desk endpoint ("status on job x", "progress on this build")

**Have**
- The Sep 14 job API had `/check_jobs`, `/job/{id}`, `/stats`, `/eta` from measured medians (MEASURED working then).
- The 27B.

**How it should work: the database answers, the model only phrases**
- A **Front Desk** preset: a ~300-token system prompt, reasoning off, and only read-only tools: `job_status(id|name)`, `recent_events(n)`, `queue_summary()`, `whats_due()`, `system_health()`. No shell, no memory writes, no model loading.
- Each tool returns structured facts (state, step k of n, last event, ETA from `runs` medians, blockers, pending approvals). The model restates them.
- **If a fact is not in the tool output, the answer is "I don't have that"; never a guess.** Tested with a promptfoo suite of trap questions ("what's the status of job 999?").
- **Even faster:** a plain `/status` command and a control-room tile that need no model at all (instant, zero hallucination risk). The model is for natural phrasing and follow-ups.
- **Slot:** one of the 27B's two parallel slots is reserved for you. The batch semaphore never takes it (W2).

**Which model**
- The 27B. The small 1.7B could phrase templates but is weaker; not worth it while the 27B is resident.
- Latency: time-to-first-token for a short prompt with reasoning off is **not measured** on the current config (VERIFY). Section 7 has read-only ways to get it from existing logs.
- Estimate: well under 2 s for a status answer, if reasoning is off. **xhigh reasoning on a status question is the biggest avoidable delay**, because the model thinks before it answers. Turning it off is a per-request setting (`chat_template_kwargs`), not a server change. VERIFY the template honours it per request.

### N9. Constantly watch for new models that could run here, even tight, and alert me for fast-house batches

**Have**
- Jarvis's `hf_model_sizes` tool (every quant's byte size for a list of repos) and `web_search`.
- The dated watch list and neutral rankings in `model-benchmark-dataset` (Artificial Analysis index v4.3.2, ceiling 53).
- Months of fit arithmetic in the wiki, and the proven fast-house pull-script workflow.

**How it should work: code decides "can it run", the model writes the digest**
1. **Poll, don't subscribe.** Hugging Face webhooks need a public URL, and nothing here should be public. Sources, each daily:
   - the Hugging Face models API for the uploaders that matter (unsloth, ggml-org, bartowski, mradermacher, ubergarm, ISTA-DASLab, kernelpool, and whoever you add), sorted by creation date, GGUF or safetensors only;
   - llama.cpp and ik_llama.cpp release feeds (`https://github.com/ggml-org/llama.cpp/releases.atom`) and merged PRs mentioning a new architecture;
   - the Artificial Analysis leaderboard for neutral scores.

   Rate limits on the public Hugging Face API without a token: VERIFY.
2. **The fit check is arithmetic in code, against the `models` table and measured constants.** Tiers, from easy to "only if everything else is off":
   - one V100;
   - both V100s;
   - one CPU socket (≲230 GiB);
   - both sockets beside Jarvis (≲ RAM minus Jarvis minus headroom);
   - whole box with Jarvis off (≲~490 GiB with GPU offload, the MiMo pattern);
   - streaming experts from disk (llama.cpp PR #25294, unmerged; SOURCE: HANDOFF).

   Checks include:
   - **Architecture supported** in the production llama.cpp build, a known fork, or not at all (grep the architecture name in upstream source through the GitHub API).
   - **Volta traps:** no FP8/NVFP4, no BF16 on GPU, CUDA ≤12.9 (what-not-to-do #2, #13).
   - **Pickle check:** refuse `.bin`/`.pt` pickle checkpoints (Part 4 hard boundary).
3. **Speed estimate from measured constants, labelled ESTIMATE.**
   - Formula: decode ≈ effective bandwidth ÷ bytes read per token.
   - Effective bandwidth: ~37 GB/s interleaved, the GLM-5.3 calibration (MEASURED); ~62% of STREAM on this box.
   - Prefill is flagged "unknown" until benchmarked. The GLM results show prefill is the real wall, so it cannot be skipped.
4. **Quality:** use Artificial Analysis if listed, or "vendor-only, unverified" if not. Keep the benchmark traps from model-benchmark-dataset (never compare SWE-bench Verified to Pro, and so on).
5. **Alerts:**
   - Immediate phone alert only when a model fits AND beats the model in some slot on a neutral score, or fills a missing slot.
   - Everything else goes to a weekly digest.
   - Each candidate becomes a draft line in a "fast-house batch" manifest (repo, files, bytes, why, which slot it would replace, which benchmark decides it). You approve the batch; nothing downloads by itself.

**Which model:** mostly none: this is code. The 27B phrases the digest; an optional GLM-5.3 pass once a week writes a deeper "is this worth a slot" note.

**Risks**
- Leaderboard drift: benchlm read ±0.5 on the same day.
- Vendor numbers presented as neutral.
- The box's architecture support is the real gate: new families often need weeks of unmerged PRs (GLM-5.3-Flash is still fork-only).

### N10. A voice that talks as fast as a real human (the Iron Man Jarvis)

**What "human speed" means:** conversation research puts the typical gap between turns at ~200 ms, with ~500 ms feeling natural and ~800 ms like a thoughtful pause. Production voice agents in 2026 measure ~680 ms median and ~1.2 s p95 (SOURCE: [WebRTC.ventures latency budget, Sep 2026](https://webrtc.ventures/2026/09/voice-ai-latency-budget/) and search summaries). Budget per stage: turn detection 150-300 ms, speech-to-text final 50-100 ms, LLM first token 150-400 ms, text-to-speech first audio 100-200 ms, network 30-80 ms.

**Have**
- Open WebUI voice mode: local Whisper in the container, replies spoken sentence by sentence (W1, SOURCE: Open WebUI docs via jarvis-system-build).
- ASR models and audio.cpp GGUFs on the drive.
- Kokoro may be on the drive (pull_addendum listed it; VERIFY).

**Options found**
- **Pipecat** (BSD-2, ~15.9k stars): a full-duplex voice pipeline with interruption handling and "smart-turn" end-of-turn detection. It supports local Whisper, Kokoro, Piper and any OpenAI-compatible LLM, with WebRTC or websocket transports (SOURCE: [github.com/pipecat-ai/pipecat](https://github.com/pipecat-ai/pipecat)).
- **Speaches** (MIT, ~3.7k stars): an OpenAI-compatible speech-to-text and text-to-speech server (faster-whisper; Kokoro and Piper), CPU or GPU, with a realtime API (SOURCE: [github.com/speaches-ai/speaches](https://github.com/speaches-ai/speaches)).
- **Speech-to-text on CPU:** Moonshine (built for streaming, ~100 ms class latency) and NVIDIA Parakeet TDT 0.6B v3 are far faster than Whisper-large on CPU (SOURCE: [Northflank 2026 comparison](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks), [Moonshine vs Whisper](https://modelslab.com/blog/audio-generation/moonshine-vs-whisper-asr-real-time-speech-2026)). Haswell (no AVX-512) is slower than those test machines: VERIFY.
- **Text-to-speech:** Kokoro-82M runs ~0.03 real-time factor on a GPU, but **~1-2 s for one short sentence on a CPU** (SOURCE: [GigaGPU](https://gigagpu.com/tts-latency-benchmarks/) and search snippets of a CPU benchmark; the CPU model is unstated). On your older Xeons, CPU text-to-speech will likely be the slowest stage (ESTIMATE).

**Realistic numbers** (ESTIMATE, nothing measured)
| Setup | Voice-to-voice |
|---|---|
| Today's pieces: Open WebUI voice mode, Whisper base on CPU, Kokoro on CPU, 27B with xhigh reasoning | ~2-5 s (reasoning alone can add seconds) |
| Pipecat + Moonshine/Parakeet on CPU + 27B reasoning off + Kokoro on CPU | ~1.2-2.5 s |
| Same with speech-to-text and text-to-speech on a GPU (needs the freed card, see below) | ~0.7-1.3 s |
| Sub-500 ms "human" | **Not reachable** with a 27B through a speech-to-text → LLM → text-to-speech chain on V100s. Speech-to-speech models or a tiny model would be needed, and they cost the intelligence you want. |

**How it should work**
- A **Voice** preset: very short prompt, reasoning off, one or two sentences per reply, and the same read-only front-desk tools plus `submit_job` (which goes through the N1 gate: voice can start an interview, never skip it).
- The phone client is a browser page (installed to the home screen as a web app) over Tailscale, or the iOS Vocal Shortcut "Hey Jarvis" for push-to-talk (W13).
- **The single biggest hardware lever is freeing a GPU:** the planned single-card 27B A/B (orchestrator-slot-plan, benchmark-campaign Phase B). With one V100 free, speech-to-text plus Kokoro fit easily and both become ~100 ms class (ESTIMATE). The trade-off: a single-card 27B means a smaller quant or context. That is a benchmark question, not settled.

**Risks**
- Voice turns share the 27B with the front desk and batch jobs. The reserved slot matters even more here.
- A microphone on your phone plus network hops: Tailscale on cellular adds 50-150 ms (ESTIMATE).

### N11. Weave Jarvis into your life: check any account, do anything you could do

**Honest scope first:** "anything I could do" is not possible, and parts of it are not allowed by your own rules:
- graded schoolwork stays off-limits: read due dates, extract, tutor, check afterwards, drill (Part 4);
- anything that sends, buys, posts or deletes needs your approval;
- logins, 2FA prompts and CAPTCHAs are "stuck, human needed" handoffs (T4).

What is realistic is read access to most accounts plus approved actions.

**Options found**
- **Gmail**
  - **Gmail API + OAuth:** a Google Cloud app left in "Testing" status issues refresh tokens that **expire every 7 days** for Gmail scopes (SOURCE: [Google OAuth docs](https://developers.google.com/identity/protocols/oauth2), [explainer](https://www.unipile.com/google-oauth-refresh-token/)). Moving to "Production" removes that. Whether a personal, unverified production app with Gmail's restricted scopes is allowed without Google's security review is **VERIFY**. Budget time for this; it is the most common way home Gmail integrations silently die.
  - **Simpler for reading:** IMAP with an app password (needs 2-Step Verification on the account; VERIFY app passwords are still offered for your account).
  - **Sending:** SMTP with the same app password, always through an approval.
- **Google Calendar:** the calendar's secret iCal address gives read-only access with no OAuth. Writing events needs the API and OAuth.
- **School systems** (D2L Brightspace, Cengage/MindTap)
  - Read due dates only. D2L has a calendar subscription feed (VERIFY it lists your items; notes say D2L's calendar renders empty). Cengage has no feed known here.
  - Scraping with a real browser session is possible, but Cengage runs bot detection (Part 4). Even read-only scraping carries some risk to your account. **Your decision.** Low frequency (once a day), read-only.
- **n8n** (self-hosted workflow automation, 400+ integrations): since v2.6 (Jan 2026) its AI agent can require human approval per tool, via Gmail, Slack, Telegram or chat (SOURCE: [n8n docs](https://docs.n8n.io/advanced-ai/human-in-the-loop-tools/), [2026 guide](https://www.triggerworkflow.com/2026/08/n8n-human-in-the-loop-approval-guide.html)). Its licence is "fair-code" (Sustainable Use License, not OSI open source: VERIFY terms). It would be a second approvals system beside yours, so it is not recommended as the core. It is useful later for quick integrations whose actions still route to your approvals queue.

**How it should work**
- **Credentials:** stored only by `jarvis-core` (files mode 600, or systemd-creds). They are used by small "connector" tools that return data. `jarvis` never sees a raw password, so a prompt injection in an email cannot leak it (GAP 3).
- **Every connector starts read-only.** Actions go through approvals. Trust graduation is per action type (T1: e.g. after N clean approvals you may promote "add calendar event" to automatic, and never "send email").
- **Email is also an injection surface:** anything read from email or web pages passes the prompt-injection classifier before a tool-holding model sees it (orchestrator-slot-plan; the model is on the drive if pull_orch finished, VERIFY).

### N12. An interactive, cool-looking control room: job progress and what happens behind the scenes ("prompt routed to jarvis_3 (glm 5.3 flash)")

**Have**
- The W4 design: Claude writes the spec, Jarvis writes the code; one SSE endpoint; a single file; no CDN (jarvis-system-build).
- The Sep 14 supervisor stamped each response with `_jarvis_route` {label, slot, port, reason}. It is gone now, but the idea carries straight into the `events` table.

**How it should work**
- **One source of truth: the `events` table (section 2.2).** Every component writes an event when it acts:
  - the router ("routed to `glm53` because 'hard review', confidence 0.91");
  - the admission controller ("unloading flashnext to load glm53, ETA 3 min");
  - the worker ("job 12 step 3 tests 14/15 passed");
  - approvals and health.

  The UI is a live view of that table (Server-Sent Events) plus a few live readings:
  - `nvidia-smi` and `free`;
  - llama-swap's `/running` and its log stream;
  - llama-server `/slots` and `/metrics`. Production needs `--metrics`, a small unit change for your approval later (SOURCE: [server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)).
- **Panels:**
  - jobs (spec, step k/n, ETA, last grounded check);
  - routing feed;
  - slots (what's loaded where, RAM/VRAM bars);
  - approvals (with the phone flow);
  - health (red when something is ABSENT, GAP 1);
  - the kill switch.
- **Slot names:** friendly names (`jarvis_1` = 27B GPU, `jarvis_3` = GLM-5.3-Flash, ...) live in the `models` table, so the feed can say exactly what you wrote.
- **Access:** the UI is read-only except approvals and the kill switch, which need your credential. It is served on the tailnet only.
- **Trace drill-down, optional later:**
  - **Arize Phoenix** runs as one container and is built on OpenTelemetry, but it is Elastic License 2.0 (source-available, not OSI).
  - **Langfuse** is MIT but needs Postgres + ClickHouse + Redis + S3 to self-host (SOURCE: [Langfuse comparison](https://langfuse.com/faq/all/best-phoenix-arize-alternatives), [morphllm comparison](https://www.morphllm.com/comparisons/arize-phoenix-vs-langfuse)).
  - Neither is needed for v1. The `events` + `steps` tables already carry the "what went where" story.

**Which model:** the 27B builds it through N2 (spec, sandbox, tests, approval). The reviewer checks it in the headed browser (console clean, DOM assertions, screenshot) before you see it.

### N13. Models reviewing each other until the job is really done; a bigger model that knows 100% what I want reviews, and I approve its suggestions on my phone

**Have**
- The key finding from GVS5H's code: its "review" is running the solution against tests, not a model's opinion. Ungrounded model-on-model review converges on confident, well-structured wrongness (W3, SOURCE: GVS5H multiagent.py via jarvis-system-build).

**How it should work**
1. **The loop:**
   1. The builder produces an artifact.
   2. **Grounded checks** run: tests; page load + console + DOM + screenshot for websites; re-fetch for research; manifold and wall thickness for prints.
   3. The **reviewer** gets a fresh context holding only: the approved spec, the acceptance tests, your answers from the interview, your standing preferences (a `preferences` table built from past approvals and denials), the artifact, and the check results.
   4. The reviewer returns a structured verdict:
      - `pass`;
      - `fix_list`: things that violate the approved spec, which go straight back to the builder, no need to bother you;
      - `suggestions`: changes to the spec or ideas beyond it, which **go to your phone as approve/deny**.
2. **Stopping rules, in code:**
   - max iterations (start at 5);
   - a no-progress detector (the same failing checks twice in a row);
   - a wall-clock budget;
   - a "cannot ground this" exit that hands the job to you with what was tried (T4).
3. **"A model that knows 100% what I want":** its knowledge is exactly the approved spec plus the interview plus your preferences, nothing more.
   - Before it reviews, run the N1 comprehension quiz against it. If it cannot answer your intent questions, it does not review.
   - You can quiz it yourself from the control room ("what did I say about mobile?").
   - 100% is not achievable. "Passed your quiz and the auto-quiz" is achievable and measurable.
4. **"Models talking to each other"** means structured hand-offs through the database and the job workspace (plan, notes, artifacts, verdicts), not open-ended model-to-model chat. Free chat between models drifts, costs tokens, and leaves no audit trail. The ledger pattern is the one with evidence behind it (GVS5H; Anthropic's verification-subagent note in deep-research-optimization).

**Which model**
- The reviewer should be a **different family** from the builder, for real diversity (W3): builder Qwen (27B or Flash-Next), reviewer GLM.
- GLM-5.3 is measured at 1.0-1.5 t/s, so it gives **one final review per build** (~1.5-2.5 h per call, ESTIMATE), not every iteration.
- In-loop reviews: GLM-5.3-Flash if the fork build works (unmeasured), otherwise Flash-Next (same family as the 27B, so less diversity; the grounded checks carry most of the weight).
- Website visuals: Qwen3-VL-4B on CPU (on the drive, unmeasured), and the model's opinion never overrides a console error (orchestrator-slot-plan).

**Phone:** section 2.6. Each suggestion is one notification with Approve/Deny. "Deny with reason" and batch review open the approvals page.

### N14. Never break, never kill the server, never touch what keeps Jarvis working ("maybe I can make these behind sudo access")

**Have**
- Good habits already measured on this box: systemd units with memory caps and OOM priority for experiments; no pkill; backup before editing a unit; test on a spare port.
- The supervisor rule "only signal PIDs you started" (jarvis-orchestrator).
- The tool-server output cap.

**Missing** (what the incident log proves prompts cannot do)
- The fences in section 2.1.
- An off-box backup.
- A health watchdog.
- The kill switch.
- The bind fix.

**How it should work: the full list, each item a structural guard**
| Guard | What it stops | Status |
|---|---|---|
| Separate `jarvis` user for the shell, no sudo; production units root-owned; polkit allows `jarvis-sandbox-*` only | Jarvis stopping llama-server, Open WebUI, the database, the backups | not built |
| Tool server bound to `172.17.0.1` (docker0) instead of `0.0.0.0` | anyone on your LAN getting a root-less but unrestricted shell | your decision, pending (HANDOFF) |
| Also: llama-server (8080) and Open WebUI (3000) listen on all interfaces | LAN users querying the model or the UI without going through Tailscale | VERIFY; your decision |
| `MemoryMax` on every non-production unit; `OOMScoreAdjust=1000` on experiments; a strongly negative value on production llama-server | a big-model load OOM-killing Jarvis | pattern MEASURED for benchmarks; production value not set (VERIFY) |
| Admission controller (section 2.4) | two big models plus Jarvis exhausting RAM; a GPU render during a two-card load (15 A circuit, GAP 4) | not built |
| Nightly restic backup **off-box** (Backblaze B2 now, NAS later); SQLite via `.backup` / `VACUUM INTO`; monthly restore drill | a dead NVMe; a bad edit; a deleted database | not built (W19, #1 on your board) |
| Git for `~/jarvis-memory`, configs, prompts; `etckeeper` for `/etc`; pre-edit copies (ADD 6) | a bad edit to memory, prompts, units | partial (manual .bak files) |
| Health watchdog on the *absence* of things (llama-server, Open WebUI, tool server, job API, disk, SMART, backup age) | silent death, like the 20-minute Open WebUI outage nobody noticed | not built (GAP 1) |
| Kill switch target plus phone action (section 2.7) | a runaway loop while you are away | not built |
| Per-action rate limits (ADD 3) | job storms, notification floods, portal hammering | not built |
| Driver and kernel updates held; unattended-upgrades excludes nvidia/cuda (and the kernel, unless DKMS is proven) | an update breaking the V100 stack (driver 580 is the last for Volta) | your decision, pending |
| Staging: test ports, sandboxes, approval to promote, one-command rollback | a self-build breaking the live system | not built |
| Model drive in fstab with `nofail`, read-only | a reboot silently dropping the drive (and a boot hang if it is missing) | pending (HANDOFF) |

**"Behind sudo" done right:** Jarvis gets **no** sudo. Wide NOPASSWD sudo is how a jailbroken prompt becomes root. You already have the fence you want in the account boundary itself: you keep sudo, Jarvis cannot use it.

A few read-only diagnostics already have passwordless sudo for `simon` (`nvme smart-log`, `journalctl`, `dmesg`; MEASURED Sep 14 on the old box). Those can move to the watchdog user rather than to `jarvis`.

**Honest limit:** "never" is not reachable against hardware. Single points of failure remain:
- one NVMe, no RAID;
- one PSU;
- a 15 A basement circuit;
- the USB model drive;
- the end-of-life Volta driver.

The design makes failures contained (fences), noticed (watchdog), and recoverable (backups, rollback). Jarvis may still break *its own* sandbox or memory; that is acceptable because it is fenced and in git.

**Conflict with your earlier choices, stated plainly:** on Sep 21 you chose an unrestricted shell, and on Sep 22 full memory control. The fences keep both, but inside the `jarvis` user. The one thing that changes: Jarvis can no longer operate on the box *as you*. Some things it did as `simon` (reading `~/bench`, managing your files) will need either read access granted to it or you. That is the decision in section 9.

### N15. Smooth, visible, no glitches, and especially no hallucinations

**Honest bottom line:** zero hallucinations is not achievable with any current model, local or frontier. On AA-Omniscience, which subtracts for confident wrong answers, every local model here scores at or below zero: the 27B −10, Flash-Next −10, GLM-5.3 +14; for comparison Claude Opus 5 +37 (model-benchmark-dataset, SOURCE: AA). What *is* achievable:
- the system never states facts about itself that aren't in the database;
- research claims are always cited, checked, and flagged when unsupported;
- you can see every step.

**Controls, by where hallucinations come from**
| Source | Control |
|---|---|
| Questions about Jarvis itself (status, what ran, what's loaded) | Answer only from the database tools (N8). "I don't have that" when absent. promptfoo trap tests. |
| World facts in chat | No answers from memory for facts that matter: retrieval with citation, or "unverified" marked. |
| Research and review claims | A verbatim quote per claim; groundedness checker; re-fetch sample; numbers never paraphrased (N6). |
| Tool output cut off | Already fixed: the tool server returns head+tail with an explicit TRUNCATED marker (MEASURED, jarvis-run-host-commands). |
| Context overflow, silently losing history | 4 silent truncations in 48 h (MEASURED). Keep jobs out of chat; ctxwatch alerts; long work lives in the database; reasoning off for short roles. |
| Fake tool calls when Open WebUI function calling is "Default" | The jarvis model row now has native function calling (MEASURED, Part 5). Keep it in the promptfoo suite so a regression shows up. |
| Model restating a number | Numbers are copied, and derived numbers are computed by code (research spec rule). |

**Groundedness checkers found**
- **HHEM-2.1-Open** (Vectara's cross-encoder, ~0.44 GB, CPU, needs `trust_remote_code`): the pick recorded in orchestrator-slot-plan.
- **MiniCheck:** the 770M FT5 version reaches GPT-4-level accuracy on the LLM-AggreFact benchmark in its paper, and a stronger Bespoke-MiniCheck-7B exists (SOURCE: [github.com/Liyan06/MiniCheck](https://github.com/Liyan06/MiniCheck), [arXiv 2404.10774](https://arxiv.org/abs/2404.10774)).
- Measure the chosen checker's false-pass rate on **RAGTruth** (queued in pull_research, VERIFY on the drive) before relying on it.
- The generative phi3.5 hallucination judge on the drive is a second opinion that explains, never the gate.

**"Smooth" and "no glitches"**
- The health watchdog (alerts on absence), the control room (visibility), and the kill switch.
- Regression suites run before any prompt, flag or model change (ADD 2).
- The glitch that bites most today is context truncation. It is solved by moving work out of the chat, not by a bigger window, which the GPUs can't hold (HANDOFF).

---

## 4. The 24 Part 4 wants, mapped onto this design

Most are covered by an N-section above. The rest keep the plans already in the wiki; this table says where each stands and what it depends on.

| # | Want | Where covered / what it needs | Depends on |
|---|---|---|---|
| W1 | Voice dispatcher from the phone | N10 | Front-desk tools, reasoning-off preset; freed GPU for best latency |
| W2 | Two jobs at once while talking | Batch semaphore: the 27B runs `--parallel 2`, so at most 1 batch job on the 27B plus your reserved slot. CPU big models are separate slots. Aggregate throughput with 2 parallel requests is not measured (benchmark-campaign "concurrency"). | Job worker |
| W3 | Models review models, grounded | N13, section 2.5 | Grounding checks per job type |
| W4 | Control room | N12 | `events` table |
| W5 | YouTube video pipeline | Keep the wiki plan (video-generation-v100): Wan 2.2 recommended; PyTorch cu126 wheel only; no BF16/FP8; flash attention is a known NaN source on Volta for LTX. Clip generation needs a **whole GPU** → a Jarvis-off window or the freed card. The heavy-GPU lock (GAP 4) forbids a render during a two-card LLM load. | Exclusive GPU slot, admission controller, approvals for posting |
| W6 | Training AI (QLoRA) | Unsloth on Volta, fp16, 7-9B target; llama-server can serve LoRA adapters (finetuning-and-rpc-pooling). Needs an exclusive GPU window and **data (W22)**. | W22 corpus, GPU window |
| W7 | AI inside your websites | A separate public preset: no tools, no memory, its own port, auth, rate limit; precompute content overnight and serve it static. Gates: Qwen3Guard, prompt-injection classifier. Never the Jarvis preset. | Fences, a static host; public exposure is your decision |
| W8 | Teaching and diagnosis | `skills` table from real graded work only; drill locally; deep conceptual teaching escalates (the local ceiling, W9); N7 video finder | Learner model; never graded work |
| W9 | Escalation ladder | 27B → Flash-Next / GLM (single-shot, N3) → frontier for what neither clears, arriving prepared. A **budget counter** caps frontier spend (GAP 5). | Router, frontier API decision |
| W10 | AR glasses | A later client of the voice stack; capture-only first; deliberate single captures (image prefill makes streaming impractical) | N10 |
| W11 | Robotics | Model → tool → broker (Home Assistant REST / MQTT) → device; limits in firmware; every actuation logged and approval-gated at first | Fences, approvals |
| W12 | 3D printer end to end | OpenSCAD code path; headless slicer; mechanical checks (manifold, walls, overhangs, plate fit); print-watching by camera. **Which printer you bought is still unrecorded** (Bambu needs LAN-only + Developer Mode). | Your printer model |
| W13 | "Hey Jarvis" | iOS Vocal Shortcuts (no code) → POST to the voice or front-desk endpoint over Tailscale; openWakeWord `hey_jarvis` for a home device (no published error rates; measure in your room) | N10 |
| W14 | Email and calendar triage | N11 | Account decisions |
| W15 | Marketplace watches | Saved searches as scheduled jobs; ntfy on a hit. Facebook only via a paid proxy scanning service, never your login. eBay has an official Browse API (free developer account; VERIFY terms). Craigslist feeds: VERIFY current availability. | Scheduler, a paid-service decision for Facebook |
| W16 | Workout reminders and diet | Scheduled nudges plus a plan you approve (approvals table) | Scheduler, ntfy |
| W17 | Location nudges | Deprioritised (your call, Sep 14) | n/a |
| W18 | Music taste | Deprioritised | n/a |
| W19 | Backup and recovery | Roadmap step 1: restic nightly off-box, SQLite-safe, restore drill | A target decision |
| W20 | Daily audit log | The `events` table + the tool server's command log (exists: `~/jarvis-run-host-commands.log`) → a daily digest; logs backed up off-box | Events table |
| W21 | Overnight goal research | N6, scheduled; one goal per night | N6 |
| W22 | Writing capture | **Start now, it gates W6.** A drop folder + an export of your own messages from Open WebUI chats, tagged by source. Only text you wrote yourself, because AI-assisted text would teach the model its own style. | Nothing (a script) |
| W23 | Build your own AI | Learning track: microgpt first, then micrograd, makemore, nanoGPT on a V100 (needs a GPU window) | GPU window |
| W24 | Uncensored model for hardening | A separate preset, no tools, no memory, no secrets. HauhauCS Q5_K_P is on the drive, but its FastMTP patch is required (model-download-manifest). Red-team **advisor** for your own box only. | Fences (what-not-to-do #23) |

**Also on your board, and time-critical: the schoolwork due-date tracker.** It is the only item with a real external deadline, and it still has zero code (Part 4 priority 2).
- It must not depend on experimental services (GAP 6): its own small unit, its own table, and ntfy.
- The roadmap puts it right after the job spine, because it reuses the scheduler and notifier and nothing else.

---

## 5. Conflicts between wants, and what cannot be done as asked

1. **Unrestricted shell as `simon` (Sep 21) vs "never break".** Both cannot hold. The fences keep the shell unrestricted, but as `jarvis`. **Decision D1.**
2. **"100% every time" interview vs speed.** The gate is 100%. The interview's *quality* is measured, not guaranteed. A full interview for every tiny job will cost you time; express checklists per type are the release valve. Voice may *start* an interview; it can never skip one.
3. **Big models for building vs their speed.** GLM-5.3 is measured at 1.0-1.5 t/s decode and ~2.5-10 t/s prefill. Each call is ~1.5-2.5 h (ESTIMATE). It can do single-shot pieces and final reviews, never agent loops. Flash-Next's real speed is the open question that decides how much building moves off the 27B.
4. **"Load MiMo on demand" vs "Jarvis always on".** MiMo needs both GPUs and ~489 GiB RAM, so Jarvis must be off while it runs. It is also not joined yet, and there is no disk space to join it. It can only ever be a scheduled, approved event.
5. **Human-speed voice vs a capable model vs VRAM.** Sub-500 ms voice-to-voice is not reachable with a 27B via speech-to-text → model → text-to-speech on V100s. ~0.7-1.3 s probably is (ESTIMATE), and only with a freed GPU.
6. **Every GPU want competes for the one card the re-layout might free:** voice (N10), uncensored model (W24), video (W5), fine-tuning (W6), nanoGPT (W23), and the Qwen3-VL-32B vision slot. Only one of them can be the resident tenant; the rest take scheduled windows. **Decision D13.**
7. **Front desk "fast" vs xhigh reasoning.** Reasoning must be per role: off for front desk and voice, high for building and review.
8. **"Use every resource" vs the RAM rule (Jarvis + one big model), the 15 A circuit, and ~62 GB free NVMe.** The admission controller will say no often; it says why, on the control room and on your phone.
9. **"Do anything I could do" vs your hard boundaries.** Graded work is excluded by your rule. Send/buy/post/delete need your approval. Logins, 2FA and CAPTCHAs need you.
10. **"Jarvis downloads it itself" vs home bandwidth, NVMe space and your fast-house batching.** Default: Jarvis prepares the manifest and you approve.
11. **"No hallucinations" vs measured model behaviour.** Every local model scores ≤0 on AA-Omniscience except GLM-5.3 (+14). The design controls, grounds and flags. It cannot reach zero.
12. **"A reviewer that knows 100% what I want."** It knows exactly what is written in the approved spec, the interview and your recorded preferences. Your quiz makes that measurable. 100% is not a reachable number.
13. **Always-on RSI vs your chat speed and vs "never break".** RSI is batch, lowest priority, sandboxed, and promotes only with your approval.
14. **The benchmark campaign vs the orchestrator build.** Both want Jarvis-off windows and RAM. You set benchmarks first; most of the safety steps in the roadmap need no downtime, so both can proceed. The heavy steps are placed after the benchmark windows.
15. **Public websites (W7) vs a box that holds your accounts and a shell.** Keep public inference off this box, or strictly separated (its own preset, user, port and auth). Precomputed static content is the safe default.

---

## 6. Models and slots: who does what, with the evidence

"Measured" means on jarvis-1. Everything else is labelled.

| Role | Model | Where it runs | Speed evidence | Status |
|---|---|---|---|---|
| Front desk, interviewer, voice, orchestrator | Qwen3.8-27B Q4_K_M + MTP | 2x V100 (production 8080) | **Today: decode 42-79 t/s (typical 45-58), prompt reading 343-722 t/s, MTP acceptance 0.67-0.98 (MEASURED Sep 25, section 1a).** Time-to-first-token ≈ prompt tokens ÷ ~500 t/s + reasoning. | Resident |
| Router / classifier / triage | Qwen3-1.7B Q4_K_M (A/B: Qwen3.8-2B distill), grammar-forced labels + log-probability confidence, no tools | CPU | Not measured. "Well under a second" per label (ESTIMATE, jarvis-orchestrator). | On drive (slots/) |
| Worker for long-context building and reading | Qwen3.8-Flash-Next UD-Q4_K_XL (+MTP via the PR build) | CPU, socket 1 beside Jarvis | ~5-6 t/s beside Jarvis, ~10 interleaved (ESTIMATE). **Prefill unmeasured**, which is the deciding number. | On NVMe, not hashed |
| Hard single-shot pieces, final review, nightly synthesis | GLM-5.3 UD-Q4_K_XL | CPU, both sockets; exclusive | **1.48 t/s decode interleaved (Jarvis off), 0.9-1.1 beside; prefill ~10 → ~2.5 t/s from empty to 16K (MEASURED)** | On NVMe, verified |
| In-loop reviewer (other family), mid rung | GLM-5.3-Flash UD-Q4_K_XL | CPU, one socket | Not measured; needs the Unsloth fork build | On NVMe, not hashed |
| Rare "ask one hard question" event | MiMo-V2.6-Pro MXFP4 | Whole box, Jarvis off | ~2-5 t/s (ESTIMATE, SOURCE wiki); nothing measured | Raw parts on drive; needs join + ~519 GiB free disk |
| Groundedness gate | HHEM-2.1-Open (or MiniCheck) | CPU | Milliseconds per pair (SOURCE: wiki); not measured here | On drive (verify/HHEM-2.1-open) |
| Retrieval | Embeddings + reranker (0.6B wide, 4B final) | CPU | Not measured | On drive (embed/, verify/) |
| Safety filters | Prompt-injection classifier; Qwen3Guard-Gen-4B for public presets | CPU | Not measured | Both on drive (verify/) |
| Website visual check | Qwen3-VL-4B | CPU | Not measured | On drive (verify/) |
| Speech-to-text / text-to-speech | Moonshine or Parakeet (or Whisper), Kokoro-82M | CPU now; GPU after the re-layout | Not measured; CPU text-to-speech likely ~1-2 s per short sentence (SOURCE snippets) | On drive: faster-whisper large-v3/turbo, whisper.cpp, ASR slot, Kokoro ONNX + GGUF |
| Red-team advisor | HauhauCS 27B Uncensored | GPU window or the freed card | Not measured; FastMTP patch required | On drive |

**What would change this table:** the Flash-Next day-1 queue (already written: docs/bench/queue-fn.txt) and the llama-server harness (KV per token, MTP, `--parallel`, time-to-first-token). **The benchmark session owns those; this plan depends on their results.**

---

## 7. VERIFY: read-only checks that settle open questions

Each one reads only. None starts, stops, installs, writes or edits anything. Best run when no benchmark is running (a few read the disk).

| # | Settles | Command |
|---|---|---|
| V1 | Who can do what today: groups and sudo rights | `id simon; getent group sudo docker; sudo -l -U simon` |
| V2 | What listens on the LAN (8080, 3000, 8200, others) | `sudo ss -ltnp` |
| V3 | Current units and their settings | `systemctl list-units --all 'jarvis*' 'llama*' 'bench*' --no-pager; systemctl cat llama-server jarvis-run-host-commands --no-pager` |
| V4 | Whether production is protected from the OOM killer | `systemctl show llama-server -p OOMScoreAdjust -p MemoryMax -p Restart` |
| V5 | Free space and memory right now | `df -h / /mnt/models; free -g` |
| V6 | Which small models and datasets actually landed on the drive | `ls /mnt/models/models/slots /mnt/models/models/embed /mnt/models/models/verify /mnt/models/models/audio 2>&1 \| head -80` |
| V7 | Whether HHEM, RAGTruth, Kokoro and the injection classifier are on the drive | `find /mnt/models/models -maxdepth 4 \( -iname '*hhem*' -o -iname '*ragtruth*' -o -iname '*kokoro*' -o -iname '*injection*' -o -iname '*simpleqa*' \) 2>/dev/null \| head -40` |
| V8 | Which corpora landed (PMC, PubMed, Wikipedia ZIM) | `ls -la /mnt/models/models/corpus /mnt/models/models/data 2>&1 \| head -60` |
| V9 | Current 27B speed per request (prompt and generation timings from real chats) | `journalctl -u llama-server --since "-24h" --no-pager \| grep -E "prompt eval time\|  eval time\|draft acceptance" \| tail -30` |
| V10 | Whether reasoning can be switched off per request (chat template) | `curl -s http://127.0.0.1:8080/props \| python3 -c "import json,sys; print(json.load(sys.stdin).get('chat_template',''))" \| grep -n -i -E "reasoning\|enable_thinking" \| head` |
| V11 | Whether `/slots` and `/metrics` are enabled | `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/slots; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/metrics` |
| V12 | Driver/kernel update exposure | `apt-mark showhold; uname -r; dkms status; grep -v '^\s*//' /etc/apt/apt.conf.d/50unattended-upgrades \| grep -v '^\s*$' \| head -40` |
| V13 | Tailscale exposure | `tailscale serve status; tailscale status \| head -20` |
| V14 | Firewall state | `sudo ufw status verbose; sudo nft list ruleset \| head -60` |
| V15 | Backup tooling present; key files exist (names only, never print keys) | `restic version; ls -la ~/.config/jarvis/` |
| V16 | Did the headed-Chrome/CDP browser stack survive the rebuild | `systemctl list-units --all --no-pager \| grep -i -E "chrome\|xvfb\|vnc\|browser"` |
| V17 | Open WebUI version (for voice mode and pipe-function support) | `sudo docker inspect open-webui --format '{{.Config.Image}} {{.Created}}'` |
| V18 | Model drive USB link speed (load-time estimate) | `lsusb -t` (then, only when idle, a read-only speed test: `sudo hdparm -t /dev/sda`) |
| V19 | NVMe PCIe link (load-time estimate) | `sudo lspci -vv \| grep -A40 -i "non-volatile" \| grep -E "LnkCap:\|LnkSta:"` |
| V20 | GLM-5.3 load time from NVMe (if the glm-test server was ever started) | `journalctl -u glm-test --no-pager \| grep -i -E "load time\|loaded\|listening" \| head` |
| V21 | Open WebUI web search backend | Look only: Admin → Settings → Web Search |
| V22 | D2L calendar feed / Gmail app passwords | In your browser: D2L Calendar → Subscribe; Google Account → Security → App passwords (look, don't create) |

---

## 8. Summary table

Effort estimates (ESTIMATE):
- **S** = one evening
- **M** = a few evenings
- **L** = weeks

These assume Jarvis writes most of the code from Claude-written specs, with you pasting root-level steps.

| Want | Have | Need | Recommended approach | Effort | Blockers |
|---|---|---|---|---|---|
| N1 Spec interview, 100% | 27B; Sep 14 approvals design; interview spec pattern | Gate, checklists, restatement check, comprehension quiz | Database gate + worker check + approval only via your credential; checklist-driven interview saved per turn; echo check in code; fresh-model quiz | M | Fences (D1) so the model can't write the DB; job spine |
| N2 Self build/improve | create_tool, write_file, GVS5H proven | Sandbox, promotion step, scorer | Self-change = job type: spec → sandbox → tests → approval → promote with backup | M | N1, fences, scorer |
| N3 Fresh-context big-model jobs | GLM-5.3 measured; Flash-Next copied | Executor, briefs, artifacts | Worker builds a brief, one fresh call, stores the artifact, runs tests; GLM single-shot only | M | Flash-Next numbers; llama-swap |
| N4 Any model on demand, incl. MiMo from HDD | All files; `-lm dio`; systemd-run pattern | llama-swap, admission controller, `models` table, resource requests | llama-swap wrapping systemd-run; controller enforces RAM/GPU/power rules; MiMo only as an approved Jarvis-off event | M (MiMo: L) | MiMo join needs ~519 GiB of disk; Jarvis off |
| N5 Always-on RSI | Mutation half; bench queue | Unwritable scorer, held-out set, lineage, caps | `jarvis-eval` user; promptfoo + KLD baselines; GEPA on prompts first; approval to promote | L | Fences; the scorer must catch a planted regression first |
| N6 Deep research overnight | Research spec; web_search; possibly local corpora | Crawl worker, claim table, gates, search API | Build to RESEARCH-SPEC (or start with local-deep-research); Tavily + Brave credits + Serper; GLM synthesis at night | M-L | Search accounts; Flash-Next speed; groundedness checker on drive |
| N7 Tools like the YouTube finder | Learning protocol; ACT pack | `skills` table, YouTube API key, transcripts, reranker | Misconception → search → transcript grounding → 27B check → 1-3 timestamped picks | M | Google Cloud project; your graded work as input |
| N8 Fast front desk | 27B; Sep 14 job API design | Read-only status tools, a reasoning-off preset | Database answers, model phrases; `/status` with no model at all | S (after spine) | Job spine; V10 (per-request reasoning) |
| N9 New-model watcher | hf_model_sizes; watch list | Pollers, fit checker, digest | Code-only fit tiers from measured constants; weekly digest; fast-house manifest | S-M | None major |
| N10 Human-speed voice | Open WebUI voice mode; ASR on drive | Streaming pipeline; fast speech-to-text and text-to-speech; freed GPU | Pipecat + Moonshine/Parakeet + Kokoro; reasoning off; GPU after the re-layout | M | Freed GPU for sub-1.3 s; sub-500 ms not possible |
| N11 Accounts and life | Nothing live | Connectors, credential broker, approvals | Read-only connectors first; sends via approvals; trust graduation | M per account | Gmail OAuth 7-day trap; Cengage bot risk (D11) |
| N12 Control room | Design from W4 | `events` table, SSE page | Everything writes events; single page on the tailnet; Phoenix optional later | M | Job spine |
| N13 Review loop + phone approvals | GVS5H grounding insight | Grounded checks per type, reviewer, approvals push | Build → checks → other-family reviewer (fresh, spec-only) → fixes auto / suggestions to phone; caps | M-L | GLM speed; GLM-5.3-Flash fork build |
| N14 Never break | Good unit habits; output cap | Users/permissions, bind fix, backups, watchdog, kill switch, holds | Section 2.1 fences + N14 table | M | Your decisions D1-D4 |
| N15 No hallucinations, smooth | Output cap; native function calling | Database-only status; groundedness gate; regression suites | Section N15 controls table | M | Checker on drive (V7) |
| W1-W24 | See section 4 | See section 4 | See section 4 | varies | Mostly the spine + fences |
| Schoolwork tracker | Nothing live | Scraper/feeds, deadlines table, ntfy | Its own isolated unit; Cengage > D2L precedence; read-only | S-M | D11 (scrape risk); feeds |

---

## 9. Decisions you need to make

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | The permission fence | (a) keep Jarvis's shell as `simon` (today); (b) move it to a new `jarvis` user with full control of its own home and memory, no sudo | (b). It is what makes "never break", the spec gate and the unwritable scorer real. Also decide what of `/home/simon` `jarvis` may **read** (e.g. `~/bench/results`, `~/models` read-only). |
| D2 | Network exposure (V2/V14: no firewall, 8080/3000/8200/111 on every interface) | Tool server → `172.17.0.1`; 8080 → loopback + docker0; 3000 → loopback + Tailscale; a host firewall (careful: Docker manages its own nft rules) | Bind the tool server now. Then a firewall that allows SSH and Tailscale and drops the LAN on 8080/8200/111. |
| D3 | Off-box backup target | Backblaze B2 now (restic, encrypted); NAS (ESC4000) later; both | Both: B2 now (pennies for configs, databases, memory, units); NAS as the second copy once it has caddies. Keep the restic password somewhere off the box. |
| D4 | Freeze the GPU stack | `apt-mark hold` the NVIDIA driver packages; add them to unattended-upgrades' Package-Blacklist | Hold the driver. Kernel updates can stay: DKMS already rebuilt 580 for 6.8.0-142 (MEASURED). |
| D22 | `lxd` group membership (section 1a) | Remove `simon` from `lxd` if LXD is installed (V24); never put `jarvis` in it | Remove, if V24 shows LXD installed. |
| D23 | Production OOM protection | Give llama-server a strongly negative `OOMScoreAdjust` (and later run it as its own user) | Yes, with the next deliberate production-unit edit (backup + spare-port rule). |
| D5 | HF token on the model drive | Revoke and re-issue, or keep | Revoke (it is plain text and readable by any user). |
| D6 | Notifications | ntfy.sh public topic (as Sep 14) vs self-hosted ntfy + upstream for iOS | Self-hosted, auth deny-all; approvals via one-time tokens. |
| D7 | Frontier top rung | None / Claude API or similar with a hard monthly cap | A cap of ~$10-15/month inside your $25, used only for audits of syntheses and truly stuck jobs. |
| D8 | Search APIs | Tavily (free 1,000/month, no card); Serper (2,500 free); Brave ($5 credit, card required) | Tavily + Serper first; add Brave only if you accept a card on file. |
| D9 | Interview rules | Which job types get "express" checklists; the echo threshold; whether voice may start interviews | Express for timer-class tasks only; voice may start but never skip. |
| D10 | First accounts to connect, and how | Gmail via IMAP app password vs OAuth; calendar via secret iCal URL | Read-only IMAP + iCal first; sending later through approvals. |
| D11 | School portals | D2L feed if it works; Cengage scraping (bot-detection risk) or manual | D2L feed; Cengage once daily read-only only if you accept the risk, otherwise you paste the list. |
| D12 | MiMo | Pursue (needs disk and Jarvis-off windows) or park | Park until the other big-model numbers are in; if pursued, the cheapest disk is an internal recertified SATA HDD (section 10). |
| D13 | Who gets the freed GPU (if the single-card 27B A/B passes) | Voice; uncensored; video; fine-tuning; Qwen3-VL-32B | Voice resident; the others in scheduled windows. |
| D14 | RSI scope | Prompts only; + flags via the bench queue; + sandboxed code | Prompts first. Code only after the scorer catches a planted regression. Every promotion needs your approval. |
| D15 | Build order vs the schoolwork tracker | Tracker right after the spine, or later | Right after the spine (real deadlines). |
| D16 | System prompt safety sections 13/14/19 | Restore in Open WebUI | Restore (still pending from Part 5). Prompts don't enforce, but they reduce how often the fences have to. |
| D17 | Model drive at boot | fstab read-only with `nofail` | Yes (HANDOFF pending). |
| D18 | Downtime windows | Share the 1-7 AM Central window between benchmarks and orchestrator heavy steps | Benchmarks keep priority; the orchestrator's early steps need no downtime. |
| D19 | YouTube | Create a Google Cloud project + API key; approve a channel allow-list | Yes when N7 starts. |
| D20 | n8n | Adopt as core / later for integrations / no | Not as the core; maybe later. |
| D21 | Printer | Which 3D printer you bought (W12) | Tell me when W12 comes up. |

---

## 10. What to buy or download

### Paid services (ceiling ~$25/month)
| Item | Cost | Why | Label |
|---|---|---|---|
| Backblaze B2 (restic target) | $6.95/TB/month (raised from $6.00 in Mar 2026); egress free up to 3x stored. Configs + DBs + memory + units are likely <20 GB → **<$0.15/month** | Off-box backup (W19) | SOURCE: [B2 pricing](https://www.backblaze.com/cloud-storage/pricing), size ESTIMATE |
| Tavily | Free 1,000 credits/month, no card; $0.008/credit after | Research search | SOURCE |
| Serper | 2,500 free credits (6 months), then ~$1 per 1,000 | Research search | SOURCE |
| Brave Search API | $5/month credit (~1,000 queries) free; card required; billed beyond | Optional third engine | SOURCE |
| YouTube Data API | Free (100 searches/day) | N7 | SOURCE |
| Frontier API top rung | Cap at ~$10-15/month | W9 audits | ESTIMATE; your decision D7 |
| Pushover (only if ntfy's iOS approval bug annoys you) | $4.99 one-time per platform | Fallback approvals app | SOURCE: [pushover.net/pricing](https://pushover.net/pricing) |
| **Expected monthly total** | **~$0.15-$15**, depending on D7 | | ESTIMATE |

### Hardware (none required for the core plan)
| Item | Cost | Why | Notes |
|---|---|---|---|
| Internal recertified CMR SATA HDD, 8-14 TB | historically ~$73-135 each (wiki, not verified live) | A home for the joined MiMo file (~557 GB), a cold model library, and an on-box backup tier (not off-box) | Uses a free SATA port. **VERIFY how the G2GPU12 chassis mounts and powers a 3.5" disk.** Never SMR. |
| or a 2 TB NVMe with DRAM | e.g. Samsung 990 PRO 2 TB ~$338 on Amazon (Sep 2026); others lower | Faster MiMo loads (~2-3 min vs ~40-60 min from HDD) | SOURCE: [Tom's Hardware best SSDs](https://www.tomshardware.com/reviews/best-ssds,3891.html) listing; the board is PCIe 3.0, so a Gen4 drive gives no extra speed. Needs the $14.99 PCIe x4 adapter (wiki SKU 099994). Never DRAM-less (what-not-to-do #19). |
| NAS caddies for the ESC4000 (ASUS 13GS1I0AM063-1) | VERIFY | The NAS as the second backup copy | Part 5 |
| UPS | VERIFY | A clean shutdown on a power blip (the NVMe history) | The wiki says a 900 W unit is undersized (power-thermals-and-tuning) |
| Optional: 2x Xeon E5-2699 v4 | ~$150-240 the pair (wiki; VERIFY live and board BIOS support) | Speed for every CPU model | Not needed for any want; a speed lever only |

### Downloads (for a fast-house batch; sizes ESTIMATE unless marked)
Check V6-V8 first. Several of these may already be on the drive from pull_orch / pull_research / pull_addendum.

| Item | Size | For | Label |
|---|---|---|---|
| llama-swap release binary | ~15-30 MB | N4 model manager | ESTIMATE |
| restic binary (if not installed) | ~25 MB | W19 | ESTIMATE |
| ntfy server binary | ~30-40 MB | Section 2.6 | ESTIMATE |
| Pipecat (pip) + faster-whisper/ctranslate2 + onnxruntime | ~0.5-2 GB with deps | N10 | ESTIMATE |
| Moonshine (base) and/or Parakeet TDT 0.6B v3 | ~0.25 GB / ~0.6-2.5 GB | N10 speech-to-text | ESTIMATE |
| ~~Kokoro-82M~~ | already on the drive (ONNX and GGUF; section 1a) | N10 | MEASURED |
| Speaches container image (optional alternative to Pipecat's local services) | ~2-5 GB | N10 | ESTIMATE |
| ~~HHEM-2.1-Open~~ | already on the drive | N15 | MEASURED |
| MiniCheck-FT5 (optional second checker) | ~3 GB (770M params, fp32) | N15 | ESTIMATE |
| ~~prompt-injection deberta~~ | already on the drive | N11/N6 | MEASURED |
| Playwright + its Chromium build (the Sep 14 browser stack is gone) | ~0.3-0.5 GB | N6 page reading, N13 website review | ESTIMATE |
| FRAMES (RAGTruth and SimpleQA are already on the drive) | small | Calibrating the gate and research accuracy | ESTIMATE |
| promptfoo (npm), lm-evaluation-harness (pip), GEPA (pip) | ~0.3-1 GB total | Scorer (N5) | ESTIMATE |
| Arize Phoenix image (optional, later) | ~1-2 GB | N12 trace drill-down | ESTIMATE |
| Python wheels for the job spine (fastapi, uvicorn, httpx are already in use; add pydantic, sse-starlette) | small | Spine | ESTIMATE |

**No new big models are recommended now.** The next model decisions wait on the Flash-Next and llama-server-harness benchmarks.
