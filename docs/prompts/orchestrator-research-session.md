I'm Simon. This session is a RESEARCH session for my local AI system, Jarvis, on my home server jarvis-1. Another Claude Code session is running the model benchmarks at the same time; do not touch that work.

Setup:
1. Run: git fetch origin claude/new-session-uyo1y3 && git checkout -b claude/orchestrator-research origin/claude/new-session-uyo1y3
   Work, commit and push ONLY on claude/orchestrator-research. Never push to claude/new-session-uyo1y3 (the benchmark session owns it). Do not edit docs/HANDOFF.md, docs/bench/ or docs/benchmarks/.
2. Read in full, in this order:
   - docs/orchestrator-wants-simon-2026-09-25.md (my wants, verbatim: THE GOAL of this session)
   - docs/HANDOFF.md (the box, the rules, current state)
   - docs/jarvis-briefing-2026-09-25-part4.md (my 24 earlier wants, hard boundaries, self-improvement plan)
   - docs/jarvis-briefing-2026-09-25-part5.md (verified box facts; wins on conflicts)
   - docs/benchmark-campaign.md and docs/benchmarks/*.md (what is measured so far)
   - docs/wiki/README.md, then the wiki pages relevant to each want (jarvis-orchestrator, orchestrator-slot-plan, agent-harnesses, jarvis-system-gaps, jarvis-what-not-to-do, local-eval-harness, deep-research-optimization, prompt-cache-and-prefill-reuse, context-and-speed-per-model, and others as needed)

The task:
Research how to make the Jarvis system meet EVERY want in my wants document (and the 24 in Part 4), given the hardware and software I actually have. For each want:
- What I already have that helps (on the box, on the model drive, in the wiki research).
- What is missing or has to change (software, models, hardware, services, accounts), with the best current options found by web research: open-source projects, agent frameworks, voice stacks, routers, eval harnesses, UIs, phone approval apps, and anything else relevant. Prefer mature, maintained, local-first options. Give links.
- How it should work structurally so it is reliable. Examples: the spec interview is enforced by the job queue refusing unapproved specs, not by a prompt; hallucination control through grounding and verification; "never break" through users, permissions, sudo fences, backups and staging, not through instructions.
- Which model or slot should do it, using measured benchmark numbers where they exist and saying clearly where they do not yet.
- Risks, conflicts between wants, and anything that cannot be done as asked, said plainly.
Then write:
- docs/orchestrator-research.md: the full findings, per want, plus a summary table (want / have / need / recommended approach / effort / blockers).
- docs/orchestrator-roadmap.md: an ordered build plan. Safety and backup foundations first (off-box backup, tool-server bind fix, permission fences, kill switch, a scorer Jarvis cannot edit), then the job queue with enforced spec approval, then the rest. Each step small, testable, and reversible.
- A list of decisions I need to make, and a list of anything I would need to buy or download (with sizes and costs; my paid-services ceiling is about $25/month; downloads happen in batches at a faster house).

Rules:
- Call me Simon. Older notes and files on my model drive call me "Jack"; that is me, but never use that name. "Jackrong" is a Hugging Face uploader, not me.
- My time zone is Chicago (Central). Give all times in Central.
- Label every claim MEASURED (on my box), SOURCE (read in code or docs, with a link), ESTIMATE, or VERIFY. Say plainly when something is wrong, unchecked, or not possible. Accuracy over reassurance.
- This session is research and planning ONLY. Do not give me commands that change jarvis-1. If a read-only check on the box would settle a question, list it in the research doc as a VERIFY item with the exact read-only command.
- You cannot reach jarvis-1. Anything on the box goes through me.
- Never do my graded schoolwork (my rule). Tutoring, due-date tracking and exam prep are fine.
- No model identifiers in commits or files.
- Commit and push as you go, so nothing is lost if the session ends.

When you have read everything, reply with a short summary of how you will approach it and any questions, then start.
