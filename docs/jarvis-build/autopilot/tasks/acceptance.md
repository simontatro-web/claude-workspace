Acceptance run for the autopilot and the context proxy.
Read ~/ctxtest/TASK.md and follow it exactly: 25 edits, in order, one commit each.
If you see CONTEXT HIGH, update the RESUME HERE block and keep going.
If you see CONTEXT COMPACTED, run `git -C ~/ctxtest log --oneline | head -3` before anything else and continue
from the next uncommitted edit. Never redo a committed edit.
Every claim you make must quote the command output that proves it.
The task is complete when all 25 edits are committed and `git -C ~/ctxtest status --short` prints nothing.
