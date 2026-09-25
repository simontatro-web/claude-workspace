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
4. **"Does it really understand?": test it, don't trust it.** After you approve, a **fresh** model instance that sees only the spec (not the chat) answers an automatic quiz generated from your interview answers ("what happens when a student gets a question wrong?"). Wrong answers mean the spec document does not carry your vision, and the gap goes back to you before the build starts. This is also exactly your later idea of quizzing the big reviewer model (N12). It matters because every downstream model gets only the spec, never the chat.

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
- "Incorporating what they built" is done by the worker plus tests plus the reviewer (N12), and promotion needs your approval. The small model never "pastes it in" unchecked.
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
- **Conflicts with N13 ("never break") by nature.** It is only compatible because promotion needs your approval and the production units are out of its reach.
