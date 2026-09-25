# jarvis-system-gaps

> Copied verbatim from Cowork (melange-wiki) on Sep 25 2026 (page last updated Sep 14, 2026).
> Cowork-only links kept as page names.
>
> Summary: Cross-cutting infrastructure gaps in the jarvis-1 build that NONE of the 24 feature-wants cover but ALL of them depend on — health monitoring, an approval mechanism, secrets, power-awareness, frontier-cost budget, and staging. Plus quality-of-life items. Claude's Sep 14 2026 review of the whole system. Read alongside jarvis-system-build.

Companion to jarvis-system-build (the 24 wants). Jack asked Sep 14 2026 for a gap review of the whole system. These are things every feature assumes but nobody specced. Ordered by how badly their absence bites.

## GAP 1 — HEALTH MONITORING: who watches the services. THE MOST PROVEN GAP, because it already bit tonight.

The audit log (WANT 20) records what Jarvis DID. Nothing records what SILENTLY STOPPED. Everything is systemd services, and tonight the supervisor died on shutdown and the embedding server did too, and the only reason that is known is a human was watching. In production nobody is. NEEDS: a heartbeat/healthcheck worker that pings each critical endpoint (llama-server 8080, supervisor 8100, Open WebUI 3000, browser-tools 8090, each scraper's last-success timestamp) on a schedule and ntfy-alerts on a MISS. Negative-space monitoring: the alert fires when something is ABSENT, which is the opposite of the audit log and the control-room UI (both of which only show what IS happening). Include a "scraper has failed N days running" tripwire, since a silently-broken tracker is exactly the expensive failure Jack named for the schoolwork piece.

## GAP 2 — AN ACTUAL APPROVAL MECHANISM. Every "confirm before acting" want assumes this and it does not exist.

WANTS 14 (email send), 15 (marketplace buy), 7 (website changes), and Jarvis's whole "act on his behalf but confirm first, every time" rule all assume Jack can approve an action FROM HIS PHONE. There is no approval queue anywhere in the design. Without it, "confirm first" degrades to "do nothing while he is away", which defeats the autonomy. NEEDS: an `approvals` table and a flow — worker writes a pending action, notifier pushes it, Jack approves/denies, worker proceeds or drops. ntfy supports ACTION BUTTONS in notifications (verify current capability), so a push can carry Approve/Deny inline without opening anything. This is a small piece that unblocks a large fraction of the board, and it is the correct home for the confirm-before-acting rule — enforced by the queue, not by asking the model to remember.

## GAP 3 — SECRETS MANAGEMENT. A real hole, made worse by WANT 24.

The system will hold: D2L logins, Gmail/Google OAuth, the marketplace proxy service, ntfy topic, and likely a frontier API key for rung 3. Right now these would live in plaintext in scripts or the Open WebUI DB. On a box that is internet-adjacent (Tailscale funnel for the public websites, WANT 7) AND runs an uncensored shell-enabled model (WANT 24), plaintext credentials are the obvious thing an attacker or a jailbroken model reads first. NEEDS, in ascending order of effort: at minimum a single `.env` with `chmod 600` outside any web-served path and out of git; better, `pass`/`age`/systemd-creds; the rule that the uncensored preset and any public preset get NO access to the secrets path, same isolation as their no-tools/no-memory rule.

## GAP 4 — POWER-AWARENESS. This is jarvis-1's own physical worst case and no scheduler knows about it.

From local-ai-setup: the box is on a 15A basement circuit; 2 uncapped V100s plus fans approach 11.4A against a 12A NEC continuous limit, which is why `nvidia-smi -pl 200` is mandatory. Now stack the plan on top: a GPU video render (WANT 5, exclusive slot), GLM on CPU pulling hard (WANT 9), and both cards loaded, ALL AT ONCE, is an unmodelled power spike. Tripping the breaker mid-write on a single-drive box is precisely the uncontrolled-shutdown scenario that corrupts filesystems — the exact risk the whole nvme-drive-failure saga is about. NEEDS: the job scheduler must be power-aware to the extent of a simple mutual-exclusion rule — never run a GPU video/training render CONCURRENTLY with a sustained two-card LLM load. Cheapest version: a global "heavy GPU job" lock so only one runs at a time. The 240V circuit Jack has considered is the real fix; until then the scheduler is the guard.

## GAP 5 — FRONTIER-RUNG COST BUDGET. The only rung that costs money is unmetered.

The escalation ladder (WANT 9) tops out at Claude/frontier, which is real API spend or usage. Nothing counts or caps it. An autonomous system that escalates freely can quietly run up cost. Jack's stated paid-services ceiling is ~$25/month (local-ai-setup). NEEDS: a counter on rung-3 calls with a monthly budget, logged to the `runs` table, surfaced on the control room, and a hard stop (fall back to GLM) when the budget is hit. Ties to the "measuring stick" eval discussion — you also want to know rung 3 is being spent only where rungs 1-2 genuinely failed, not reflexively.

## GAP 6 — STAGING vs PRODUCTION. He will be building 24 features on the ONE box Simon depends on.

The schoolwork tracker is load-bearing for a real student with real deadlines, and every other want is developed on the same machine. Breaking llama-server while wiring up the video pipeline takes the tracker down too. Tonight already showed how easily a shared box gets disrupted (three production-server kills). NEEDS: not a second machine, but discipline encoded — the tracker's data path (scrapers → DB → ntfy) should NOT depend on the experimental services, so that breaking the coding harness cannot silently stop schoolwork alerts. Isolate the load-bearing path from the playground.

## QUALITY-OF-LIFE, lower stakes but real

- Session-start state read for Jarvis. Three incidents tonight partly because a fresh Open WebUI chat has no memory of prior chats. A short "on session start, read operating-state + open jobs" instruction in the system prompt makes each new chat continuous instead of amnesiac.
- ntfy action buttons (see GAP 2) double as the approval UI — worth confirming the feature and using it everywhere a yes/no is needed.
- Phone home-screen PWA. Open WebUI over Tailscale works; adding it to the iPhone home screen as a PWA makes "talk to Jarvis" a one-tap thing, which matters for the Siri-style WANT 13.
- A single morning digest tying it together: what's due, what jobs ran overnight, what the goal-research (WANT 21) found, what needs approval. This already half-exists in schedule-and-reminders; make it the one surface Jack reads each morning.
- Data retention/pruning. Jobs, findings, captured writing, logs and research briefs accumulate on the drive he is worried about. A monthly prune job. Minor, but it is write-and-storage load on the contested drive.

## THE META-POINT to tell Jack

Every gap here is INFRASTRUCTURE, not a feature. The 24 wants are what the system DOES; these six are what keeps it ALIVE, HONEST and SAFE while it does them. They are unglamorous and they are what separates a system that runs unattended from a demo that works while you watch it. GAP 1 (health) and GAP 2 (approvals) are the two that most change whether the whole thing is trustworthy when Jack is not looking — which is the entire point of building it.

Sep 14 2026: Jack ACCEPTED all six gaps for incorporation into the build. Treat GAPS 1-6 as build items alongside the 24 wants, not as optional.

## SECOND-ROUND ADDITIONS — Sep 14 2026, Jack asked to brainstorm more after accepting the six. Six more, filtered hard for genuine value not padding.

### ADD 1 — A GLOBAL KILL SWITCH / PAUSE-ALL. The safety primitive the whole autonomous system lacks.

Distinct from the per-actuator e-stop (WANT 11) and from stopping one process. A single trusted command, reachable FROM HIS PHONE, that halts ALL autonomous activity at once: pause the scheduler, stop draining the job queue, cancel in-flight non-critical jobs, freeze actuators. Given shell access + autonomy + physical actuators + an uncensored model on the box, "stop everything now" must be one action, not a scramble. Implementation: a single `~/.jarvis-paused` flag every worker checks at the top of its loop, plus an ntfy-triggered or one-tap way to set it. Cheap, and it is the thing he will wish existed the first time something misbehaves while he is away.

### ADD 2 — PROMPT/PRESET VERSION CONTROL + REGRESSION CHECK. Directly evidenced tonight.

He will constantly edit the operating manual, the presets, the router prompt. Tonight ALONE the manual went 13→18 sections AND the knowledge-collection copy silently DIVERGED from the live prompt (jarvis-incidents). Prompt regression is real and INVISIBLE — a wording change quietly makes routing or refusals worse and nothing tells you. NEEDS: (a) every prompt/preset change committed to a git repo on the box so any bad edit is one `git revert` away and diffs are visible; (b) the "measuring stick" eval set (the fixed ~25-item real-work benchmark from the agent-harnesses measurement discussion) run BEFORE and AFTER any prompt edit, so "did this help or hurt" is a number. This is the measuring-stick principle turned on his OWN edits, and it is the antidote to the silent-divergence failure observed tonight.

### ADD 3 — PER-ACTION-TYPE RATE LIMITS. Loop guard for an autonomous system.

An autonomous worker or a confused model can loop — submit 500 jobs, fire 50 notifications, spawn endless research, re-scrape in a tight loop. Tonight showed benign loop-adjacent behaviour (the diff-contradiction re-check, the backslash re-testing); an unattended worker doing that against a portal or ntfy is abuse or a self-DoS. NEEDS: a simple per-action-type ceiling (max N emails/hour, max N jobs queued, max N notifications/hour); on breach, pause that action type and alert rather than continue. Pairs with the kill switch as the two "runaway" guards.

### ADD 4 — ELECTRICITY COST TRACKING. Honest, and it fits his actual finances.

The box runs 24/7 with two datacentre GPUs and sustained CPU inference. That is a real monthly power bill, and Jack is cost-sensitive (part-time/gig income, ~$25/mo ceiling on PAID services — but electricity is a cost he has not counted). A rough "this cost ~$X in electricity this month" from measured wall draw × local kWh rate, on the control room. Not a feature he asked for, but the kind of honest number he explicitly prefers over reassurance, and it may change how he schedules heavy overnight jobs.

### ADD 5 — WEEKLY RETROSPECTIVE. Self-improvement loop, and it feeds his stated goals.

A scheduled job that summarises the week: jobs run and their outcomes, what failed and why, what the overnight goal-research (WANT 21) surfaced, how the eval scores moved, what approvals he granted or denied. Two payoffs: it is the natural place to notice patterns ("the tracker scrape fails every Sunday"), and it feeds his stated wish to STUDY HOW HE LEARNS (learning-partner) and to refine the system as he goes. The morning digest is daily and tactical; this is weekly and reflective.

### ADD 6 — REVERSIBILITY FOR AUTONOMOUS FILE EDITS. Finer-grained than backup.

GAP-tier backup (WANT 19) protects against total loss. This protects against a single bad autonomous edit: any worker that MODIFIES an existing file keeps a versioned/trash copy first, so a wrong edit is recoverable without a full restore. Cheapest version: workers write through a helper that snapshots the prior version to a `~/.jarvis-trash/<timestamp>/` before overwriting, pruned on a schedule. This is the file-edit analogue of the supervisor only-kill-PIDs-I-started rule: make the destructive path structurally recoverable.

Sep 14 2026: Jack APPROVED all six second-round additions (ADD 1-6). Treat as build items.

## THIRD-ROUND ADDITIONS — Sep 14 2026. Fewer this time, on purpose. The well of high-value NEW ideas is running down, which is itself signal (see the STOP note at the end).

- T1 — TRUST GRADUATION, per action type. Directly from his stated plan and it is the mechanism that makes it real. He wants confirm-before-every-action FIRST, then graduate to full autonomy as trust builds (local-ai-setup). That graduation should be EXPLICIT and PER-ACTION-TYPE, not a global flip: reading/searching is auto from day one; sending an email or buying a part stays manual until he chooses to promote THAT action type (e.g. after N clean approvals). The `approvals` table (GAP 2) already has the data to drive it. This is the spine that lets the whole system move from assistant to autonomous without a scary all-at-once switch.
- T2 — NOTIFICATION PRIORITY + FATIGUE MANAGEMENT. A muted system is a dead system. As health alerts, approvals, deadlines, job-done pings, marketplace hits and goal-research briefs all push ntfy, he WILL get buried and mute it — and a muted Jarvis is worse than none, because he will trust it to reach him and it won't. NEEDS: priority tiers (critical alert vs FYI), immediate-vs-digest routing, and quiet hours. Only "unmissable" things (GAP 1 health, a hard deadline, an approval he is blocking) interrupt; everything else batches into the morning digest.
- T3 — SOURCE-OF-TRUTH CONFLICT RESOLUTION. Already evidenced. When D2L and Cengage disagree on a due date — and act-diagnostic-fidelity/schedule-and-reminders show D2L's calendar renders EMPTY while Cengage has the real dates — which wins? An explicit precedence rule per data type (Cengage > D2L for due dates), stored, so the tracker never silently picks the wrong one. The general principle: every fact in the DB carries its source, and conflicts resolve by a written precedence order, not by whichever scrape ran last.
- T4 — A CLEAN "STUCK, HUMAN NEEDED" HANDOFF, distinct from model escalation. WANT 9 escalates to a bigger MODEL. This is different: when the system hits a wall only a human can clear (a login, a CAPTCHA, a genuinely ambiguous choice, a repeated failure), it must STOP and hand to Jack with the context gathered — what it was doing, what it tried, what it needs — not loop, not fail silently, not guess. Same discipline as the frontier-rung "arrive prepared" rule, pointed at the human instead of the model.

## HOW THESE SIX RELATE

ADD 1 (kill switch) and ADD 3 (rate limits) are the RUNAWAY guards. ADD 2 (prompt VC + regression) and ADD 6 (edit reversibility) are the MISTAKE-RECOVERY guards. ADD 4 (power cost) and ADD 5 (retrospective) are the VISIBILITY items. Same shape as the first six: none is a feature, all are what make the features safe to leave running. The pattern across BOTH rounds: the interesting wants are what the system does; the durable value is in the boring machinery that lets Jack stop trusting it with his eyes and start trusting it with his absence.
