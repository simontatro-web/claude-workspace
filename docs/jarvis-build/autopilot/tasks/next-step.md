Do the next unfinished step in ~/jarvis-build/handoff/01-steps.md, following its spec file exactly, tests included.
First: write the step name and your 3-line plan into the RESUME HERE block of ~/jarvis-build/PROGRESS.md and commit.
Commit after every sub-task, and rewrite RESUME HERE each time.
The step is complete when its spec's tests pass (quote each summary line), PROGRESS.md records the result and any
FOR SIMON commands (each with what it changes, a test and an undo), and `git -C ~/jarvis-build status --short`
prints nothing.
Anything that needs root is FOR SIMON: finish everything else, write those commands in PROGRESS.md, commit, and end
with STATUS: DONE. Do not start a second step in this run.
