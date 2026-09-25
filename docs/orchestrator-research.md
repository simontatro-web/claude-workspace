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

Part 4 says re-measure before relying on any of them. **So the current production decode speed and time-to-first-token are VERIFY.**

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
  - `events`: an append-only log of everything that happens: "prompt routed to glm53 (reason: hard review, confidence 0.91)", "model load started", "job 12 step 3 failed tests". This one table feeds the control room (N11), the front desk (N8), the daily audit (W20) and the weekly retrospective.
- **Approvals and grounding**
  - `approvals`: pending actions (spec approval, suggestion, email send, model download, promotion to production). Approve or deny from your phone.
  - `claims`: research and review claims, each with its source, verbatim quote and gate verdict (for N6, N14).
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

### 2.5 Grounding gates (N12, N14, W3)
Every review or answer that claims a fact passes something that is not a language model's opinion:
- **Code:** tests actually run.
- **Websites:** a page load in the headed Chrome, console errors, DOM assertions, screenshots.
- **Research:** a re-fetch of the source plus a string match of the quote.
- **Groundedness:** a small checker scores every sentence against its source: HHEM-2.1-Open or MiniCheck. The status of both, and whether they are on your drive, is in N14.
- **Status answers:** read from the database, never from model memory.

### 2.6 Notifications and approvals from your phone (N12, GAP 2)
Recommended: self-host **ntfy** on the box, tailnet-only, with `auth-default-access: deny-all`. For instant iOS delivery, set `upstream-base-url: https://ntfy.sh`. Only the message ID and a SHA-256 of the topic URL go to ntfy.sh; message text never leaves your box (SOURCE: [ntfy config docs](https://raw.githubusercontent.com/binwiederhier/ntfy/main/docs/config.md)).
- **How an approval works:** a notification carries Approve and Deny action buttons. Each button is an HTTP POST from your phone, over Tailscale, to the approvals API. The POST carries a one-time token tied to that approval row, so a leaked topic cannot approve anything.
- **Known iOS bug:** the ntfy iOS app does not honour `clear: true` for http actions, so an approval notification stays on screen after you tap it (SOURCE: [ntfy issue #1728](https://github.com/binwiederhier/ntfy/issues/1728)). Workaround: the approvals API sends a follow-up "Approved ✓" message. Fallback app: Pushover (one-time $5, VERIFY price).
- **Anything bigger than yes/no** (deny with a reason, "change X") goes to a small approvals page in the control room, opened from the notification's view action.

### 2.7 The kill switch (ADD 1)
- **What:** one systemd target, `jarvis-autonomy.target`. Every autonomous unit (worker, scheduler, research, RSI, llama-swap slots) is `PartOf=` it. `systemctl stop jarvis-autonomy.target` stops all of them at once. Production 27B, Open WebUI, and the health watchdog are NOT part of it, so you never lose the chat or the alarms.
- **Belt and braces:** a pause flag (a row in the `jarvis-core` database) that every worker checks before claiming work.
- **From your phone:** a pinned ntfy "PAUSE ALL" action, plus a button in the control room. Both need your credential. `jarvis` cannot un-pause itself.
