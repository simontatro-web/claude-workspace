# jarvis-system-build — the wants backlog

> Copied verbatim from Cowork (melange-wiki) on Sep 24 2026. Cowork-only links kept as page names.
> Dated Sep 15 2026.
>
> Summary: The full backlog of what Jack wants jarvis-1 to become, captured Sep 14 2026 — the wants
> (voice dispatcher, concurrent jobs, grounded review loops, control-room UI, video pipeline,
> fine-tuning, AI-in-his-websites, teaching and diagnosis, escalation ladder, and more), the
> graded-homework boundary, and the build order. Read FIRST at the start of any jarvis-1 build session.

Architecture and layers: jarvis-orchestrator. Harness research and the job-queue design: agent-harnesses. Hardware limits: local-model-landscape (copied here as `v100-hardware-and-models.md`).

## THE GOVERNING PRINCIPLE

Today the MODEL IS THE SYSTEM: everything lives in its context window, nothing happens unless Jack types, nothing outlives the conversation. The whole build is about demoting the model to a component, with SQLite holding truth, workers acting on schedules, and the model reading and phrasing. Also: at 32 t/s every extra model call is wall-clock time, so interactive work is single-call and everything multi-call is queued batch work.

## WANT 1 — Voice dispatcher, fast, usable from his phone

Say "start coding a website X" and have a voice model reply that it handed the job to the big model, with a time estimate, while he keeps talking. Fast, reachable from iPhone. VERIFIED from Open WebUI docs Sep 14 2026:

* Open WebUI has a hands-free Voice mode; replies are read aloud sentence by sentence as they stream, so perceived latency is the first sentence, not the whole answer.
* STT: local Whisper is the DEFAULT engine, runs in the container, NO API key, sizes tiny/base/small/medium/large. Start at `base`. Long recordings are chunked and that path needs `ffmpeg`.
* TTS: any OpenAI-compatible `/audio/speech` endpoint (defaults model `tts-1`, voice `alloy`, mp3), or the browser Web API as a zero-build fallback. Kokoro-82M has that endpoint shape and was already Jack's chosen TTS (CPU, commercially licensed). This is the one service to stand up.
* Phone access needs NO new client: he already opens Open WebUI over the ts.net URL.

DECISION, reversing Claude's first recommendation: use the 27B as the voice model, not a small one. Time to a ~25-token first sentence: 27B on GPU 0.8s (32 t/s MEASURED); Qwen3-1.7B on CPU 0.8s; ~4B CPU 1.7s; ~8B CPU 3.3s. The small model buys nothing on speed and costs a lot on capability. What matters for voice is time-to-first-audio, not t/s, because TTS streams and speech is only ~3 t/s equivalent. The two reasons Claude first said "small model" are fixable: (a) prompt length — give VOICE ITS OWN PRESET with a ~300-token dispatcher prompt, and rely on llama.cpp cache reuse; (b) contention — continuous batching makes a busy server SLOWER, not BLOCKED. SHAPE: second Open WebUI preset "Jarvis Voice" → 27B, short prompt (one or two sentence replies, submit and check jobs, hand off anything substantive), tools `submit_job` / `check_jobs` / `handoff`. The 1.7B stays the ROUTER. CHEAP TEST: make the preset, set voice mode to local Whisper, talk to it.

## WANT 2 — Two jobs at once while he keeps talking

ANSWER: yes. llama.cpp batches concurrent requests into the SAME forward pass — the 27B reads ~16.5 GB of weights per pass regardless of how many sequences are in flight, so aggregate throughput scales close to linearly. INFERRED, not measured on his box; measure early. BUDGET: `n_slots 4`, `n_ctx_slot 133376`. Allocate 2 batch jobs + 1 interactive + 1 spare. THE REAL RISK IS SLOT EXHAUSTION, not slowdown: a GVS5H run is manager plus workers and can want several slots. llama.cpp QUEUES when full, so Jack would sit behind batch work. The job worker needs a hard semaphore capping total batch concurrency at 3, leaving one slot always free. Prefill is compute-bound and competes; expect stutter while pages are read, not during answering. NOTIFICATION LIMITATION: Open WebUI cannot push into a chat Jack is not looking at. So "let me know when it finishes" means ntfy to the phone plus a `check_jobs` call so Jarvis can open its next reply with the result. Wire both.

## WANT 3 — Models reviewing other models' work, fully autonomous, time-insensitive

THE CRITICAL FINDING, from GVS5H's `multiagent.py`: its "review" is NOT a model reading another model's work. `_run_samples()` runs the solution as a subprocess and compares stdout to expected output. `_sample_feedback()` returns ground truth to the loop with the exact failing case. The loop works because something OUTSIDE the models says they are wrong. A 27B reviewing a 27B mostly agrees with itself. Ungrounded review loops converge on confident, well-structured wrongness while sounding MORE certain each round.

DESIGN RULE: every job type needs a grounding signal, and the reviewer interprets that signal rather than replacing it.

* Coding → run the tests
* Website → load it in agent Chrome, screenshot, read the console, assert the DOM. He already has headed Chrome on Xvfb with a CDP bridge, so this reviewer is available today
* Research → re-fetch each cited URL and check the page contains the supporting text
* Tracker → re-scrape and diff; did the due date really move or did the selector break

A MODEL REVIEWER EARNS ITS PLACE as a second pass reasoning over grounded evidence, and when it is a DIFFERENT model (GLM reviewing Qwen = genuine diversity). STOPPING RULES, required or it burns all night: hard max iterations; a no-progress detector; a "cannot ground this" exit that flags for Jack. HONEST CEILING: some things have no cheap ground truth (is a synthesis insightful, an essay good, an architecture wise). There the reviewer is just another opinion. Sort jobs into grounded vs ungrounded before trusting any unattended.

## WANT 4 — A control-room UI showing what is happening under the surface

Show the model picking which model to use and what tasks it gives. Jack wants JARVIS to write it (unlimited local usage), not Claude. Matches the proven pattern (Sep 12: Claude wrote a SPEC, the 27B produced a working 124-line browser agent first try). DIVISION OF LABOUR: Claude writes the spec, Jarvis writes the code. A genuine v1 is possible today from data that already exists:

* `GET :8100/health` → slot occupancy, per-slot healthy flag, managed PIDs
* the supervisor stamps every response with `_jarvis_route` {label, slot, port, reason} — that IS the "watch it pick a model" feed
* `nvidia-smi` for VRAM/temp/power; llama-server slot state and token rates; SMART for a drive panel

THE SPEC MUST CONTAIN exact endpoints with VERBATIM response shapes, real numbers for the at-rest paint, design direction pinned to hex palette/typefaces/grid, ONE SSE endpoint, single file served by the existing FastAPI pattern, no CDN. ADVANTAGE: served FROM jarvis-1, so it can call local APIs directly with no sandbox/CSP restrictions.

## WANT 5 — YouTube video pipeline

Idea → one model helps PLAN → another turns the plan into prompts for a video-gen model. STALE NOTE CORRECTED: "local video generation not viable, buy b-roll via API" is probably out of date. Wan2GP lists Tesla V100 in its Docker support and runs select models in as little as 6 GB VRAM. THE ACTUAL BLOCKER IS VRAM OCCUPANCY: ~1.2 and ~1.7 GB free per card, so a 6 GB render does not fit beside the 27B. NEW CONCEPT: exclusive slots. Some slots require a GPU to themselves (video render, fine-tuning). Starting one must stop the judge with explicit confirmation, run, then restart it. NOT the banned self-termination pattern as long as it is explicit, confirmed and supervised. THE REFRAME: five of six stages work now (idea→script 27B; script→shot list 27B; narration Kokoro CPU; assembly ffmpeg; shorts OpusClip). Only clip generation is hard. BUILD THE CLIP STAGE PLUGGABLE (stock / screen capture / API / local render later).

## WANT 6 — A "training AI": give it 200-400 samples, it fine-tunes another model and shows the process

FEASIBILITY: yes. Unsloth requires CUDA Capability 7.0 (V100 named). QLoRA VRAM: 7B=5GB, 8B=6GB, 70B=41GB. KNOWN V100 BUG (unsloth issue #4082) is about FULL fine-tuning of BF16 models only; LoRA/QLoRA is fine. His recipe (NF4 + sdpa + fp16 + paged_adamw_8bit) is right. THE EXPECTATION: 200-400 samples suits STYLE, VOICE, FORMAT, TASK BEHAVIOUR — NOT teaching facts (that's retrieval's job; a fine-tune will confidently invent). His two goals (sound like him, college-essay writing) are both style tasks. TARGET: a 27B QLoRA needs ~16-20 GB, both cards exclusively, 27B unloaded. First fine-tune should be SMALL to build the pipeline. "SHOW ME THE PROCESS": live loss curve, LR schedule, held-out eval, generations from a FIXED prompt set at every checkpoint. THE HARD PART: knowing whether it helped — hold out ~20%, keep a fixed generation set, or you get vibes. THE REAL BOTTLENECK IS DATA: his corpus is "some school essays, no large personal archive". See WANT 22.

## WANT 7 — Connect the AI into websites he builds, with the AI part automated

Examples: ACT site that generates problems and diagnoses mistakes; career-discovery chat site. Ties to act-math-test-center-business and career-intelligence-platform. FIRST WANT THAT SERVES STRANGERS. Three things change: concurrency (n_slots 4 at 32 t/s; ten students queue), availability (one box on a home 15A basement circuit), exposure (public endpoint = prompt injection, abuse, no rate limit).

THE SECURITY BOUNDARY — non-negotiable: a public endpoint must NEVER reach the Jarvis preset (which has `run_host_command` = unrestricted SSH to simon@jarvis-1, plus browser and memory access). Public-facing work gets its OWN preset with NO tools, NO memory, its own port, rate limit and auth; the separation must be structural, not a prompt instruction.

THE REFRAME: most of this does not need LIVE inference. Precompute on jarvis-1, serve static. An ACT question bank: generate 1,000 items overnight as a batch job, review them, store them, serve instantly. The diagnosis half is largely precomputable via act-distractor-patterns (trap answers → error types = a LOOKUP). WHERE LIVE INFERENCE IS NEEDED: open-ended conversation (career-discovery chat). Options: (a) a small cloud model per request for anything a stranger touches, (b) jarvis-1 behind a tunnel with hard rate limits only for his own authenticated use. Content generation is just another job type; the frontend reads a DB and never talks to a model.

## WANT 8 — Teaching and diagnosis, so he can study for his tests

MOST ALREADY-SPECIFIED WANT. Protocol is verbatim in learning-partner: gauge what he knows first; teach ONE SMALL PIECE AT A TIME and pause; analogies and connected ideas; vetted YouTube videos (random/unrelated videos are extremely bad for him); quiz after and analyse answers; never combine two skills in one lesson. Plus Sep 9: do NOT pre-solve the setup, give the raw question.

THE DIAGNOSIS HALF HAS A DOCUMENTED FAILURE (act-diagnostic-fidelity): a 254-item model-generated ACT Math diagnostic had Spearman 0.26 with real official-form performance. Geometry was his WORST on the diagnostic and SECOND BEST on the real ACT (60% vs 94%). Why it failed generalises to any auto-generated diagnostic: tiny per-topic counts, uncalibrated difficulty, wrong topic weighting, structural mismatch, missing sub-skills. WHAT FIXED IT: ground truth (ACT's own category counts, four official forms). DESIGN RULE: diagnose from REAL GRADED WORK (WebAssign, MindTap, returned exams), not generated quizzes. The model's job is to EXPLAIN and DRILL, not MEASURE. Any `skills` table tags every row with its source and never mixes them into one number. THE HONEST CEILING: a 27B at 34 on AA v4.3 will NOT clear his depth bar on hard conceptual material. SPLIT THE ROLE: local for DRILL and PRACTICE (checkable answers), Claude/frontier for DEEP CONCEPTUAL TEACHING.

## WANT 9 — An escalation ladder, with the big model standing by for anything flagged

PHYSICALLY BETTER THAN EXPECTED: both models can be resident at once. GLM-5.3-Flash at UD-IQ3_XXS is 112 GiB in SYSTEM RAM; the 27B lives in GPU VRAM. GLM sits loaded on CPU while the 27B answers on GPU, so escalation costs only tokens. They barely contend (CPU uses system bandwidth, GPU uses HBM). GVS5H already ships an `escalate` engine with a `LADDER` (orchestrator.py). THE CORRECTION: GLM is ONE RUNG, not a different league (34 vs 42 on AA v4.3, and lower at IQ3_XXS). It helps on GROUNDED work (a different architecture with different blind spots), NOT on the ungrounded-depth ceiling. THREE RUNGS, TOP ONE IS CLAUDE: (1) 27B default/interactive/drill; (2) GLM flagged/hard/batch/review; (3) frontier for what neither clears. Rung 3 should be RARE AND PREPARED: arrive with context gathered, what it already tried, what specifically it is stuck on.

## WANT 10 — AR glasses as a client of the Jarvis system

SPLIT INTO TWO PROJECTS. (A) CAPTURE-ONLY glasses (camera + mic + speaker, NO display): well-trodden, cheap; BasedHardware/OpenGlass (<$25), current iteration omiGlass; multiple ESP32-S3 builds exist. Simply another CLIENT of the WANT 1 voice stack with a camera added. The 27B already has vision (mmproj auto-loads, reports text+vision+video). THE NEW COST IS IMAGE PREFILL: a vision model encodes an image into hundreds-1000+ prompt tokens; at 145 t/s prompt speed, 1024 tokens is ~7s to ingest one frame. So "what am I looking at" is a 7-10s round trip. Design around deliberate single captures, not continuous streaming. (B) See-through HUD is much harder; DIY optics is hobbyist-grade. PRAGMATIC PATH: consumer display glasses (XREAL/Rokid/Viture) present as a USB-C monitor and would just DISPLAY the control-room UI. ONE CONSIDERATION: a face-mounted camera records other people, including a young child at home and a school environment. Decide push-to-talk vs continuous before building.

## WANT 11 — Connect the Jarvis system to robotics

FIRST WANT WHERE THE AI MOVES PHYSICAL OBJECTS — a different risk class; everything else is reversible. THE CLEANEST CONTROL SURFACE: the model NEVER talks to hardware directly. Model → tool → broker/abstraction → device. That layer enforces limits the model cannot bypass, keeps device state in the DB, and logs every actuation. STACK: electrical/sensors/lights → ESPHome + Home Assistant (HA's REST API = ONE Jarvis tool); custom robotics → MQTT; ROS 2 only for serious robotics. THE SAFETY RULE: LIMITS BELONG IN FIRMWARE, NOT IN THE PROMPT (compare §13, which works only because the model chooses to follow it and failed three times first; the supervisor's PID tracking works because it is structurally incapable of doing otherwise). Every actuator: firmware-enforced range, firmware-enforced speed cap, hardware e-stop, dead-man timeout.

## WANT 12 — Jarvis drives the 3D printer end to end

Extends 3d-printer-purchase (four stages, settled, do not re-research). CARRY-OVER: use the CODE path (LLM writes OpenSCAD, executed) not mesh generation. Slicing headless via OrcaSlicer/PrusaSlicer/Bambu Studio CLI. BAMBU GOTCHA: since Jan 2025 the Authorization Control System blocks third-party WRITE commands in cloud and standard LAN mode; enable LAN-only + Developer Mode on the touchscreen (leaves MQTT, FTP, live stream open). Prompt quality decisive: "62mm bracket, two M3 holes 40mm apart" works; single objects, explicit dimensions. THE CONVERGENCE: the differentiator is a verification loop (render, check manifold-ness, wall thickness vs nozzle, overhangs, build-plate fit) — exactly WANT 3's grounded-review principle, and every check is MECHANICAL. NEW: STAGE 4, WATCHING THE PRINT, is buildable — the 27B has vision, Developer Mode leaves the live stream open; pull a frame every few minutes, ask whether it failed, halt on a positive. THE LATENCY INVERSION: the ~7s image prefill that hurts AR glasses is irrelevant for a 4-hour print. PRINTER CHOICE (STILL NOT RECORDED): P1S has only a basic camera and no AI failure detection (a local monitor ADDS capability); X1C has lidar + spaghetti detection (a monitor partly duplicates it). ASK WHICH PRINTER HE BOUGHT. Also: "find the CAD file" (search Printables/MakerWorld/Thingiverse) is often better than generating one.

## WANT 13 — "Hey Jarvis" wake word from his phone

BOTH HALVES SOLVED. (A) iPhone: iOS "Vocal Shortcuts" (Settings → Accessibility → Vocal Shortcuts, iOS 18+) gives literally "Hey Jarvis" with no "Hey Siri" prefix. The Shortcut needs no code (Dictate Text → Get Contents of URL → Speak Text); the phone is on the tailnet so it POSTs to the ts.net endpoint. CAVEATS: Apple's recognition quality (not tunable), battery cost, backgrounding unconfirmed. (B) Dedicated home device: openWakeWord ships a pre-trained `hey_jarvis` ONNX model (the wake word HA's own voice assistants use). HONEST GAP: no published false-accept/false-reject rates ("there is not a test set available to evaluate this model"); measure it in his room. LATENCY: the wake word is not the bottleneck; the model's time-to-first-sentence (~0.8s) dominates. Connects to HA Voice / Wyoming protocol (WANT 11).

## WANTS 14-18 — five things Jack stated Sep 5, missing from the first thirteen (confirmed Sep 14)

* WANT 14, EMAIL + CALENDAR TRIAGE. Read Gmail + Google Calendar (and Apple Reminders/Notes/Calendar), notice things to do, build plans, push reminders. A scheduled worker extracts action items into `deadlines`/`tasks`; model stays out of the retrieval path. Confirm-before-acting for anything that SENDS.
* WANT 15, STANDING MARKETPLACE WATCHES. Scan Facebook Marketplace, eBay, Craigslist, retail for cheapest parts. Saved query with price/radius threshold, run nightly, ntfy on a hit. RULE: Facebook Marketplace via a paid proxy-backed scanning service, NEVER his own login. Many query variants, 100-mile radius around Woodbury.
* WANT 16, WORKOUT REMINDERS AND A DIET PLAN he'll stick to. Scheduled nudges plus a plan he approves; no fitness tracker yet (maybe Apple Watch or Garmin).
* WANT 17, LOCATION-BASED NUDGES. DEPRIORITISED (needs phone location plumbing for small payoff).
* WANT 18, MUSIC TASTE ANALYSIS. DEPRIORITISED (YouTube Music, no programmatic listening history).

## WANTS 19-22 — gaps Claude raised Sep 14, all accepted

* WANT 19, BACKUP AND DISASTER RECOVERY. HIGHEST-PRIORITY ITEM ON THE BOARD. One box, one drive, no backup, and a week spent arguing whether that drive is dying (nvme-drive-failure). If jarvis-1 dies he loses the OS, models, Open WebUI DB, every chat, and `~/jarvis-memory`. A nightly off-box copy of the DB, configs, systemd units and memory store. Do this before building anything else.
* WANT 20, A DAILY "WHAT DID JARVIS DO" AUDIT LOG. Commands run, jobs executed, files changed, pages visited. For catching drift early.
* WANT 21, OVERNIGHT RESEARCH ON HIS GOALS LIST. Box idle ~8h/night. A scheduled job picks one goal, researches it, leaves a morning brief.
* WANT 22, AUTOMATIC WRITING CAPTURE — UNBLOCKS WANT 6. A job that collects everything he writes into a corpus STARTING NOW, so in three months he has ~300 samples. The binding constraint on the style fine-tune.

## WANT 23 — build his own AI from scratch, to actually understand it

A LEARNING TRACK, not a system feature. Run under the learning-partner protocol. BEST STARTING POINT: `microgpt` (karpathy, Feb 2026) — a single 200-line pure-Python file, no dependencies, trains in ~1 minute on CPU, contains the whole thing (dataset, tokenizer, autograd, GPT-2-like net, Adam, training + inference loops). PROGRESSION: micrograd → makemore → nanoGPT → microgpt (also nanochat). RECOMMENDED ORDER FOR JACK (he needs visible wins): run microgpt FIRST for the win, then go BACK through micrograd and makemore. THE ONE AREA WHERE HIS HARDWARE IS UNAMBIGUOUSLY WELL SUITED — a V100 is a real training GPU, and nanoGPT on 2x V100 is where the box stops being a constraint. Makes WANT 6 make sense: from-scratch training is the understanding, fine-tuning is the practical skill.

## WANT 24 — uncensored models for hardening HIS OWN server (scope confirmed Sep 14)

FILED SCOPE: testing a model's offensive knowledge against his OWN jarvis-1 to find and close weaknesses = ordinary defensive security. OUT OF SCOPE and Claude will not help: generating working exploits or malware aimed at systems he does not own. LEGITIMATE SHAPE: an uncensored/abliterated model as a RED-TEAM ADVISOR against his own box ("how would someone attack an exposed llama-server / a public website endpoint / this SSH setup, and how do I close it"). TWO HARD SAFETY PRACTICES:

1. A model file can execute code AT LOAD (legacy pickle checkpoints deserialize arbitrary Python). Load ONLY `safetensors` or GGUF, never `.bin`/`.pt` from an untrusted repo. The "hacking model" repos are exactly where a poisoned checkpoint would hide.
2. Abliterated models are generally DUMBER, so for real reasoning he still reaches for the 27B. Keep the uncensored model a SEPARATE preset with no tools and no memory access (a jailbroken model with `run_host_command` is its own worst-case).

HONEST CEILING: a local uncensored model is a weak penetration tester; its real value is a tutor that explains attack surface without refusing. The genuinely strong hardening moves are mundane: the public/private preset split (WANT 7), firmware-level not prompt-level limits (WANT 11), keeping `run_host_command` off any internet-facing surface, and rate limits + auth on anything exposed via Tailscale funnel.

## BOUNDARY DECISION Sep 14 2026 — doing graded homework. DO NOT DRIFT INTO THIS.

Jack asked for the AI to log into MindTap and DO HIS HOMEWORK. Claude declined, quoting Jack's own stored position (Sep 12: "for graded schoolwork he would rather lose points than risk a zero for AI use... Plain wording is not a substitute for it actually being his writing"). Completing/submitting graded MindTap work turns a lost point into a zero and an academic-integrity file; Cengage also runs bot detection that can flag his account regardless of who wrote the answers. THE LEGITIMATE SCOPE (most of the value, build it):

* READ MindTap and D2L for due dates and assignment lists — the tracker, still at zero code, highest-value item
* EXTRACT the problems into a workable format
* TUTOR him (raw question, let him build the setup, step in when stuck or wrong)
* CHECK his work AFTER he does it — where a local model is excellent and infinitely patient
* GENERATE unlimited similar problems for whatever he keeps missing — free, overnight, grounded

Framing: copied answers get him through a problem set; drilling the thing he keeps missing gets him through the exam.

## THE CROSS-CUTTING PATTERN

Wherever there is a checkable answer, local works. Wherever judgment is the product, it does not. That line runs through the review loop, the research harness, the ACT diagnostic (Spearman 0.26), teaching (drill beats conceptual depth), and the escalation ladder. Use it as the first filter on any new want.

## BUILD ORDER agreed Sep 14 2026

0. Two ten-minute items first: paste the systemd unit for the supervisor, restart the embedding server on :8102.
1. SQLite `~/jarvis.db` + the tool server. Without persistence nothing else matters. `runs` records wall-clock per job type so ETAs are measured medians.
2. Job queue + worker, generic `type` field (coding | research | review), with the 3-slot semaphore.
3. ntfy — the first unprompted phone buzz is when it stops being a chat box.
4. Scheduler, so things happen unasked.
5. Then voice preset, the harness, search, the dashboard.

COMPETING PRIORITY THAT KEEPS LOSING AND SHOULD NOT: the schoolwork tracker is the only piece with a real external deadline, has had ZERO code written, and Jack said the cost of a missed assignment is high. The orchestrator/harness work is more interesting and has no deadline. Say so when he picks. (Layers 1-4 of the build order were subsequently built Sep 14 — see jarvis-orchestrator. The tracker itself is still unbuilt.)

## WANT 19 (BACKUP) — A STAGE EXISTS BUT IT IS NOT A BACKUP. Sep 15 2026 [MEASURED]

`~/jarvis-backup-stage/` exists, created Sep 15 01:27. Contents: `config/`, `units/`, `launch/`, `misc/`, `jarvis-memory/`, `coding-harness/`, and `db/` holding `jarvis.db` (45,056 B) and `open-webui.db` (50,954,240 B). Origin unknown, NOT produced by any scheduled job — a one-off stage by a person or an agent. THREE REASONS IT DOES NOT SATISFY WANT 19:

1. It is on the SAME DRIVE as the originals; it dies with the NVMe. Protects only against accidental deletion.
2. Nothing refreshes it, so it is frozen at 01:27 Sep 15 and going stale.
3. `open-webui.db` was almost certainly copied hot; a live SQLite file copied with `cp` can be inconsistent (needs `VACUUM INTO`/`.backup` or the service stopped).

WHAT WOULD MAKE IT REAL: an off-box destination (Windows laptop, external drive, or cloud). Until a copy leaves the machine, WANT 19 remains not started. Do not let this directory read as progress.
