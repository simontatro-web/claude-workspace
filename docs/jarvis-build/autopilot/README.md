# Autopilot: Jarvis finishes a task without anyone typing "continue"

Built and tested by Claude off the box (see the tests below). Jarvis does NOT edit it. Everything below is run
by Simon on jarvis-1, after ctxproxy/README.md steps 1-6 (the proxy service is running and the Builder prompt
v2 from handoff/07-builder-prompt.md is in the preset).

## What it does
It does what Open WebUI does in a Builder chat, minus you:
- Sends the chat to Jarvis through the context proxy, so compaction and the NEW CHAT START note work. The task
  sits in the system prompt, so it survives every compaction.
- Runs his tool calls against the same tool server, behind a seatbelt (below).
- When he ends a reply without a STATUS line, it sends "continue".
- `STATUS: DONE` is accepted only if the repo has a new commit, `git status` is clean, and the optional
  `--verify` command exits 0. Otherwise it tells him what failed and he keeps going.
- If the chat ever gets too long anyway (the proxy refuses it, or it passes 600 messages), it starts a fresh
  chat for the same run: the proxy gives it a new NEW CHAT START note (RESUME HERE + git facts), and the task
  is still in the system prompt. At most 3 per run.
- It stops on DONE, `STATUS: BLOCKED: <reason>`, a limit, the PAUSE file, or `stop`, and then (if you set an
  ntfy URL) sends your phone one notification.
- Records: ~/jarvis-build/autopilot/runs/<id>/transcript.md (readable), events.jsonl (numbers), summary.json.
  Tool keys and the proxy key are never written there.

It is one run of one task that you started. It does not pick its own work and does not run on a schedule.

## Limits (flags change them)
4 hours; 250 tool calls; 40 continues; 60 tool calls without a new commit; 3 replies in a row without a tool
call; the same call giving the same result 3 times with no commit in between; 8 seatbelt refusals; 3
rejected DONEs; 3 fresh chats; model errors retried 3 times (after 5, 20, 60 s); a refused key (401/403)
stops at once.

## The seatbelt (catches accidents; it is not a security boundary, the separate users in R1.6 are)
Refuses, without running it: sudo/pkexec/su, pkill/killall, kill of llama-server, the tool server, the proxy,
the autopilot, Open WebUI, sshd or systemd (and kill with variables, jobs or groups), systemctl anything
but status/show/cat/list, reboot/shutdown, docker, apt/snap/lxc/lxd, dpkg installs, disk tools, mount,
crontab/systemd-run, anything under ~/.config/jarvis*, llama-server slot actions, git reset --hard / clean /
force-push / checkout ., rm of /, a home directory, ~/jarvis-build or a .git, writes into the proxy, the
autopilot, ~/jarvis-tools (create_tool only with --allow-create-tool), models, bench, /etc, /usr, /var,
/boot, ~/.ssh, and write tools outside ~/jarvis-build, ~/ctxtest and /tmp.

## 1. Install the command (root; once)

    sudo install -m 755 -o root -g root ~/jarvis-build/autopilot/jarvis-autopilot /usr/local/bin/jarvis-autopilot
    jarvis-autopilot help

What it changes: one root-owned script in /usr/local/bin (Jarvis cannot edit it). It uses sudo only for
`systemd-run` (so a run survives your SSH session) and `systemctl stop`; the run itself is user simon.
Test: `jarvis-autopilot help` prints the command list. Undo: `sudo rm /usr/local/bin/jarvis-autopilot`.

## 2. Tell it the tool server key (once; the key never goes to Claude)
Find where the tool server gets its key (read-only). If the output shows the key itself, replace it with XXX
before pasting it to Claude:

    systemctl cat jarvis-run-host-commands | grep -nE 'EnvironmentFile|Environment=|ExecStart'

- If you see `EnvironmentFile=/some/path` and that file holds `RUN_HOST_COMMANDS_API_KEY=...`:

      umask 077; echo 'AUTOPILOT_TOOLS_KEY_FROM=/some/path' > ~/.config/jarvis-autopilot.env

  (a different variable name: `/some/path:THE_NAME`)
- If the key is inline (`Environment=RUN_HOST_COMMANDS_API_KEY=...`):

      umask 077; systemctl show -p Environment jarvis-run-host-commands | tr ' ' '\n' | sed -n 's/^\(Environment=\)\{0,1\}RUN_HOST_COMMANDS_API_KEY=/AUTOPILOT_TOOLS_KEY=/p' > ~/.config/jarvis-autopilot.env

- Phone notifications (optional; D6 says a long random public ntfy topic is fine until self-hosted ntfy):

      echo "AUTOPILOT_NTFY_URL=https://ntfy.sh/jarvis-$(openssl rand -hex 12)" >> ~/.config/jarvis-autopilot.env
      grep NTFY ~/.config/jarvis-autopilot.env

  In the ntfy phone app, subscribe to that topic name (the part after ntfy.sh/).
Undo: `rm ~/.config/jarvis-autopilot.env`.

## 3. Preflight (read-only; uses llama-server for under a minute)

    jarvis-autopilot check

Expect `8/8 checks passed`: proxy health (new-chat note on), model list, the model answers, the model makes a
streamed tool call (nothing is executed), the tool server lists its tools, the key works (a read-only tool),
the Builder prompt v2 is found, the repo is a git repo. Paste the whole output to Claude.

## 4. First run: the acceptance task, supervised (be home, type nothing into it)

    jarvis-autopilot acceptance

What it changes: resets ~/ctxtest (25 test files), starts one transient unit `jarvis-autopilot` (gone when it
ends), and Jarvis edits ~/ctxtest and the RESUME HERE block of PROGRESS.md.
Watch (read-only): `jarvis-autopilot status` (any time), `jarvis-autopilot follow` (live; Ctrl-C stops
watching, not the run), `journalctl -u jarvis-autopilot -n 20 --no-pager`.
Stop: `jarvis-autopilot pause` (gentle: before its next model or tool call) or `jarvis-autopilot stop` (now).
Before the next run after a pause: `jarvis-autopilot resume`.
When it has ended, paste these three to Claude:

    jarvis-autopilot status
    python3 ~/jarvis-build/ctxproxy/live/check_task.py
    ~/jarvis-build/venv/bin/python ~/jarvis-build/ctxproxy/report.py --since-min 300

## 5. Gates before you rely on it (MASTER-PLAN A4)
- AP-1: three `jarvis-autopilot acceptance` runs end `done` with check_task PASS, each with 1+ compaction and
  one with 2+, and you typed nothing.
- AP-2 handoff: during a run, `jarvis-autopilot pause` once `status` shows about 12 commits. When status says
  paused: `jarvis-autopilot resume`, then `jarvis-autopilot acceptance --keep` (no reset). The new run starts
  from the NEW CHAT START note and must end `done` with PASS and no duplicate edits.
- AP-3 proxy restart: during a run, `sudo systemctl restart jarvis-ctxproxy`. The run retries and must PASS.
- AP-4 seatbelt live: `jarvis-autopilot task ~/jarvis-build/autopilot/tasks/seatbelt-test.md --no-require-commit`.
  It must end `blocked`, the transcript must show BLOCKED BY AUTOPILOT SEATBELT, and nothing else happens
  (the command it tries, `sudo -n true`, is harmless even if it ran).
- Also once in a normal Builder chat in Open WebUI (ctxproxy/README.md step 7) so the chat path is proven too.

## 6. Real work (after the gates; be home the first few times)

    jarvis-autopilot next-step                          # the next unfinished step of 01-steps.md
    jarvis-autopilot next-step --allow-create-tool      # J2b and J4, whose specs use create_tool

One step per run; you approve the next step by starting it. After each run paste `jarvis-autopilot status`
and `git -C ~/jarvis-build show --stat HEAD` to Claude. Runs while you are away: only after the kill switch
(R1.5) and the separate users (R1.6) exist (MASTER-PLAN Stage C).

## Statuses and exit codes
done (0); blocked (2); paused, limit, no_progress, stuck, seatbelt, done_rejected, stopped (3); error (4).

## Tests (Claude ran them off the box)
`venv/bin/python -m pytest -q autopilot/tests`: a scripted fake model (streamed like llama-server, tool-call
arguments split across chunks) and a fake OpenAPI tool server that really runs commands in a temp git repo;
one test puts the real context proxy in between and forces compactions; two start the real CLI (SIGTERM,
the run lock); two dry-run the jarvis-autopilot command.

## Undo everything
`sudo rm /usr/local/bin/jarvis-autopilot; rm ~/.config/jarvis-autopilot.env`; the autopilot/ folder is
in git (`git -C ~/jarvis-build log -- autopilot` shows when it came).
