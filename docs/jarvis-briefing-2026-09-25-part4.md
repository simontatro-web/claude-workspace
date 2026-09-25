# Jarvis briefing — PART 4: what Simon wants, the hard boundaries, and corrections (2026-09-25)

Companion to ~/jarvis-memory/briefing-2026-09-25.md, written by Claude for Jarvis. Same trust labels. Reference only — do not act on it unless Simon asks.

## Corrections to the main briefing
- Qwen3.8-Flash-Next speed: ESTIMATE ~10 t/s raw at UD-Q4_K_XL, ~16 t/s at GSQ-RCO IQ3_XXS, and roughly 1.3-1.6x more with the MTP draft on CPU. The higher ~18-27 t/s figure ALSO assumes NUMA mirroring, which needs an unmerged fork. Do not quote 18-27 as a stock number.
- The 29-52 t/s production range and ~630-650 t/s prefill were measured Sep 22 at -c 32768, before --spec-draft-p-min 0.4 and xhigh were added. Re-measure before relying on them.
- Docker access differs between boxes: before the rebuild simon was in the docker group (no sudo needed, so you could kill any container); after the Sep 21 rebuild docker needed sudo. VERIFY with id and groups.

## The governing idea
Today the model is the system: everything lives in the chat context, nothing happens unless Simon types, nothing outlives the conversation. The whole build demotes the model to a component — SQLite holds truth, workers act on schedules, the model reads and phrases.
The first filter on every design decision: wherever there is a checkable answer (tests, a re-fetched page, a re-scrape, a DOM assertion), a local model works. Wherever judgment is the product, it does not. Every review loop needs a grounding signal; a model reviewing a model without one converges on confident wrongness. Reviews need hard iteration caps, a no-progress detector, and a "cannot ground this, flag Simon" exit.

## HARD BOUNDARIES — never cross these
- NEVER do Simon's graded schoolwork. Do not log into MindTap/Cengage or D2L to complete or submit graded work. His own rule: he would rather lose points than risk a zero for AI use, and Cengage runs bot detection. The legitimate scope: READ due dates and assignment lists, EXTRACT problems, TUTOR him (give the raw question, let him build the setup, step in when stuck), CHECK his work AFTER he does it, and GENERATE similar practice problems for what he keeps missing.
- A public-facing endpoint must NEVER reach the Jarvis preset (shell tool, browser, memory). Public work gets its own preset with no tools, no memory, its own port, rate limit and auth — separated structurally, not by a prompt instruction. Prefer precomputing content overnight and serving it static.
- Load model weights only as GGUF or safetensors. Never .bin/.pt pickle checkpoints from untrusted repos — they can execute code at load.
- The uncensored model is a red-team ADVISOR for hardening Simon's OWN box only: no tools, no memory, no secrets. No working exploits or malware aimed at systems he does not own.
- Robotics and physical actuators: the model never talks to hardware directly (model → tool → broker → device). Limits live in firmware (range, speed cap, e-stop, dead-man timeout), never in the prompt.
- Anything that SENDS, BUYS, POSTS or DELETES on Simon's behalf needs his confirmation (via the GAP 2 approval queue once built).

## Highest priority, per Simon's own board
1. WANT 19 BACKUP — top of the board. One box, one drive, no off-box backup. ~/jarvis-backup-stage/ (if it survived the rebuild) is NOT a backup: same drive, never refreshed, and open-webui.db was copied hot. A real backup is a nightly OFF-BOX copy of the databases (via sqlite .backup or VACUUM INTO, never plain cp of a live file), configs, systemd units and ~/jarvis-memory. The restic restore was recorded as blocked; the restic key is in ~/.config/jarvis/.
2. The schoolwork tracker — the only item with a real external deadline, still zero code. Scrape MindTap/Cengage and D2L for due dates into the deadlines table; Cengage wins over D2L for due dates (D2L's calendar renders empty); ntfy reminders. It must not depend on experimental services (GAP 6).
3. WANT 22 writing capture — start collecting everything Simon writes now; it is the blocker for any style fine-tune later.

## The 24 wants (what Simon wants you to become)
1. Voice dispatcher usable from his phone: a "Jarvis Voice" preset on the 27B with a short prompt, local Whisper STT (start at base), Kokoro-82M TTS on CPU; it hands off substantive work to jobs and says so.
2. Two jobs at once while he keeps talking: cap batch concurrency so one slot is always free for chat.
3. Models reviewing models, autonomously — only with grounding (run tests, load the site and read the console, re-fetch citations, re-scrape and diff). A different model as reviewer adds real diversity.
4. A control-room UI showing routing, slots, VRAM, jobs — Claude writes the spec, Jarvis writes the code, served from jarvis-1.
5. YouTube video pipeline: idea → script → shot list → narration (Kokoro) → clips (Wan 2.2) → ffmpeg assembly → shorts. Video needs an exclusive GPU slot, started only with explicit confirmation.
6. A "training AI": 200-400 samples → QLoRA fine-tune with live loss curve, held-out eval and fixed-prompt generations per checkpoint. Teaches style/format, not facts. Realistic target on these cards is a 7-9B adapter; force fp16, never bf16.
7. AI inside the websites Simon builds (ACT practice site, career-discovery chat) — see the public-endpoint boundary above.
8. Teaching and diagnosis for his tests (see the learning protocol below). Diagnose from REAL graded work, not generated quizzes (a generated ACT diagnostic correlated only 0.26 with his real results). The model explains and drills; it does not measure.
9. Escalation ladder: 27B (default) → GLM (flagged, hard, batch, review) → a frontier model for what neither clears. The top rung is rare and arrives prepared: context gathered, what was tried, what exactly is stuck.
10. AR glasses as a client — start with capture-only glasses (camera + mic + speaker) as another voice client; deliberate single captures, not streaming.
11. Robotics — see the firmware-limits boundary. Home Assistant REST as one tool; MQTT for custom devices.
12. Drive the 3D printer end to end: OpenSCAD code (not mesh generation), headless slicing, mechanical checks (manifold, wall thickness, overhangs, plate fit), print-watching from the camera. Bambu needs LAN-only + Developer Mode.
13. "Hey Jarvis" wake word: iOS Vocal Shortcuts on the phone, openWakeWord hey_jarvis for a home device.
14. Email and calendar triage (Gmail, Google/Apple calendar): extract action items and reminders; confirm before anything sends.
15. Standing marketplace watches (Facebook Marketplace, eBay, Craigslist, retail; ~100 miles around Woodbury): Facebook only via a paid proxy scanning service, NEVER Simon's own login.
16. Workout reminders and a diet plan he approves.
17. Location-based nudges — deprioritised.
18. Music taste analysis — deprioritised.
19. Backup and disaster recovery — highest priority (above).
20. A daily "what did Jarvis do" audit log: commands, jobs, files changed, pages visited.
21. Overnight research on Simon's goals list (the box is idle ~8 h/night); a morning brief.
22. Automatic writing capture (above).
23. Build his own AI from scratch to understand it: run karpathy microgpt first (the quick win), then micrograd, makemore, nanoGPT on the V100s.
24. Uncensored model for hardening his own server (see boundary).

## How to teach Simon (learning protocol)
Gauge what he already knows first. Teach ONE small piece at a time and pause. Use analogies and connected ideas. Never combine two new skills in one lesson. Do not pre-solve the setup — give him the raw question. Quiz afterwards and analyse his answers. Only vetted, on-topic videos; random or loosely related videos are very bad for him. He needs visible wins.

## Self-improvement loop plan
You already have the mutation half (create_tool, self-restart, memory). The missing half is a SCORER YOU CANNOT TAMPER WITH: an eval harness owned by a separate root-owned user outside every path run_host_command can touch, a held-out test set the loop never sees, every change committed to git, an archive of all versions, hard fences (never touch llama-server.service, your own unit, ~/.config/jarvis/, or the backup repo), and iteration and wall-clock caps. Start with prompt optimisation (GEPA on the system prompt via llama-server on 8080). Code self-modification only after the scorer has caught a real regression. Weight self-training on your own outputs is not viable. Known failure from the literature: self-improving agents faked test logs and removed detectors — hiding the scorer is not enough, it must be unwritable.

## Other context worth knowing
- Simon's paid-services ceiling is about $25/month. Electricity cost is not a concern.
- Jarvis previously relayed through Claude driving Simon's browser; now Simon copies messages between Claude and you by hand. Claude cannot reach jarvis-1 directly.
- Open questions still open: which pre-rebuild pieces survived; whether Open WebUI has a web-search backend configured (your own web_search tool exists either way); the anti-hallucination RAG corpus was never chosen (for research, the web plus local corpora are the corpus).

END OF PART 4
