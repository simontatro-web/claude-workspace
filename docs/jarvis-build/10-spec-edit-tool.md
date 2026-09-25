# J4 spec: replace_in_file tool (small exact edits without shell quoting)

Why: editing two lines of PROGRESS.md cost a long stretch of xhigh thinking about sed/python quoting. That thinking fills your context. This tool makes an exact edit in one call.

Build with create_tool, same pattern as the delegate plugin (read it first; copy its endpoint decorator and auth; do not import pre-injected names). Copy the finished plugin into ~/jarvis-build/edittool/ so it is in git.

Endpoint: POST /replace_in_file, operation_id "replace_in_file". Body:
- path (str): expanduser; must be inside /home/simon/jarvis-build or /home/simon/jarvis-tools/plugins, else refuse. Resolve symlinks before the check.
- old (str): exact text to find. Empty old is allowed only with mode "append".
- new (str): replacement text.
- mode: "replace" (default) | "insert_after" (insert new right after old) | "append" (add new at end of file).
- expect (int, default 1): how many times old must occur. If the real count differs, change nothing and return {"error": "old found N times, expected M", "hint": first 3 line numbers where it occurs}.

What it does:
1. Read the file as UTF-8 (refuse binary or >2 MB).
2. Backup to ~/jarvis-build/.backups/<relative path>.<timestamp> before writing; add .backups/ to .gitignore.
3. Write atomically (temp file in the same dir + os.replace), keep the file's permissions.
4. Return {ok, path, replaced, backup, preview}: preview = up to 6 lines around the first change, never the whole file.
5. No shell, no subprocess.

Tests (call it as a tool, paste results):
- T1 replace a unique line in a test file under ~/jarvis-build/edittool/tests/ -> ok, file changed, backup exists.
- T2 old occurring twice with expect 1 -> error, file unchanged (compare sha256 before/after).
- T3 path /etc/hosts and a symlink in ~/jarvis-build pointing to /etc/hosts -> both refused.
- T4 insert_after under "## RESUME HERE" in a copy of PROGRESS.md -> line inserted in the right place.
- T5 text with quotes, $, backslashes and an em dash -> written exactly (sha256 of expected vs actual).

After J4, the Builder prompt rule: use replace_in_file for edits to existing files; write_file only for new files or full rewrites.

FOR SIMON: nothing to install. Add the rule line above to the Builder preset system prompt.
