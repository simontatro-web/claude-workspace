"""Tests for the autopilot: a scripted fake model, a fake OpenAPI tool server that really runs
commands in a temp folder, and (in the integration test) the real context proxy in between.

Run:  venv/bin/python -m pytest -q autopilot/tests
Every server binds to 127.0.0.1 on a free port. Nothing outside the pytest temp folders is touched.
"""
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time

import pytest
import uvicorn

HERE = os.path.dirname(os.path.abspath(__file__))
AP_DIR = os.path.dirname(HERE)
sys.path.insert(0, AP_DIR)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(AP_DIR), "ctxproxy"))

import autopilot as ap  # noqa: E402
import fakes  # noqa: E402

PROMPT = """# J1 Builder prompt (test copy)

----------
You are Jarvis, working as a builder. Keep going until the task is done. End with STATUS: DONE when the
step's tests pass and it is committed, or STATUS: BLOCKED: <reason>. This line pads the prompt so it is
long enough to pass the length check in extract_prompt, which wants at least two hundred characters.
----------
"""


# ---------------------------------------------------------------- servers

def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class ServerThread:
    def __init__(self, app):
        self.port = free_port()
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="error"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self):
        self.thread.start()
        t = time.time()
        while not self.server.started:
            if time.time() - t > 10:
                raise RuntimeError("server did not start")
            time.sleep(0.02)
        return self

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=10)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"


@pytest.fixture(scope="session")
def servers():
    m = ServerThread(fakes.model_app).start()
    t = ServerThread(fakes.tools_app).start()
    yield m, t
    m.stop()
    t.stop()


def g(repo, *a):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True,
                   capture_output=True)


@pytest.fixture
def env(servers, tmp_path):
    fakes.reset()
    m, t = servers
    repo = tmp_path / "repo"
    repo.mkdir()
    g(repo, "init", "-q")
    (repo / "start.txt").write_text("start\n")
    g(repo, "add", "-A")
    g(repo, "commit", "-q", "-m", "setup")
    fakes.TOOLS["workdir"] = str(repo)
    prompt = tmp_path / "07-builder-prompt.md"
    prompt.write_text(PROMPT)

    def settings(**over):
        s = ap.Settings(proxy_url=m.url + "/v1", proxy_key="proxykey", tools_url=t.url, tools_key="toolkey",
                        prompt_file=str(prompt), repo=str(repo), runs_dir=str(tmp_path / "runs"),
                        pause_file=str(tmp_path / "PAUSE"), write_roots=(str(tmp_path),), model="jarvis",
                        retry_backoff_s=(0.01,), task="Do the test task.", task_name="test",
                        ntfy_url=m.url + "/ntfy")
        for k, v in over.items():
            setattr(s, k, v)
        return s

    return {"settings": settings, "repo": repo, "tmp": tmp_path, "model": m, "tools": t}


def run(s):
    lines = []
    code, summary = ap.Run(s, out=lines.append, sleep=lambda x: None).execute()
    return code, summary, lines


def say(text, **kw):
    return dict(content=text, **kw)


def call(name, **args):
    return {"tool_calls": [(name, args)]}


def sh(cmd):
    return call("run_host_command", command=cmd)


COMMIT = "echo $RANDOM$RANDOM >> work.txt && git add work.txt && git -c user.name=j -c user.email=j@j commit -qm work"
DONE = say("Tests pass, committed.\nSTATUS: DONE")


def user_msgs(i=-1):
    return [m["content"] for m in fakes.MODEL["requests"][i]["body"]["messages"] if m["role"] == "user"]


def tool_texts(i=-1):
    return [m["content"] for m in fakes.MODEL["requests"][i]["body"]["messages"] if m["role"] == "tool"]


# ================================================================ the loop

def test_done_after_real_commit(env):
    fakes.MODEL["script"] = [sh(COMMIT), DONE]
    code, sm, lines = run(env["settings"]())
    assert code == 0 and sm["status"] == "done", sm
    assert len(sm["commits"]) == 1 and sm["tool_calls"] == 1 and sm["continues"] == 0
    assert fakes.TOOLS["calls"][0] == ("run_host_command", {"command": COMMIT})
    first = fakes.MODEL["requests"][0]
    assert first["headers"]["authorization"] == "Bearer proxykey"
    system = first["body"]["messages"][0]["content"]
    assert system.startswith("You are Jarvis") and "AUTOPILOT RUN" in system and "Do the test task." in system
    assert first["body"]["messages"][1] == {"role": "user", "content": ap.START_MSG}
    assert '"exit_code": 0' in tool_texts()[0]
    assert fakes.MODEL["ntfy"][-1]["title"] == "Jarvis autopilot: DONE"
    d = os.path.join(env["tmp"], "runs", sm["id"])
    assert os.path.exists(os.path.join(d, "transcript.md")) and os.path.exists(os.path.join(d, "events.jsonl"))


def test_auto_continue_without_a_human(env):
    fakes.MODEL["script"] = [say("Let me look at the task first."), sh(COMMIT), say("Edit 1 committed."), DONE]
    code, sm, _ = run(env["settings"]())
    assert code == 0 and sm["continues"] == 2, sm
    assert user_msgs(1)[-1] == ap.CONTINUE_MSG
    assert user_msgs(3)[-1] == ap.CONTINUE_MSG


def test_done_without_commit_is_rejected(env):
    fakes.MODEL["script"] = [DONE, sh(COMMIT), DONE]
    code, sm, _ = run(env["settings"]())
    assert code == 0 and sm["done_rejected"] == 1
    assert "no new commit" in user_msgs(1)[-1]


def test_done_with_dirty_tree_is_rejected(env):
    fakes.MODEL["script"] = [sh(COMMIT + " && echo junk > untracked.txt"), DONE, sh("rm untracked.txt"), DONE]
    code, sm, _ = run(env["settings"]())
    assert code == 0 and sm["done_rejected"] == 1
    assert "untracked.txt" in user_msgs(2)[-1]


def test_verify_command_gates_done(env):
    flag = env["tmp"] / "ok.flag"
    fakes.MODEL["script"] = [sh(COMMIT), DONE, sh(f"touch {flag}"), DONE]
    code, sm, _ = run(env["settings"](verify=f"test -f {flag} && echo VERIFIED"))
    assert code == 0 and sm["done_rejected"] == 1
    assert "failed (exit 1)" in user_msgs(2)[-1]
    tx = open(os.path.join(env["tmp"], "runs", sm["id"], "transcript.md")).read()
    assert "VERIFIED" in tx


def test_blocked_stops_and_notifies(env):
    fakes.MODEL["script"] = [say("I need a root step.\nSTATUS: BLOCKED: Simon must install the unit")]
    code, sm, lines = run(env["settings"]())
    assert code == ap.EXIT_BLOCKED and sm["status"] == "blocked"
    assert sm["reason"] == "Simon must install the unit"
    assert fakes.MODEL["ntfy"][-1]["title"] == "Jarvis autopilot: BLOCKED"
    assert "Simon must install the unit" in fakes.MODEL["ntfy"][-1]["body"]


def test_status_line_with_markdown_and_trailing_text(env):
    assert ap.parse_status("done\n**STATUS: DONE**") == ("DONE", "")
    assert ap.parse_status("x\nstatus: blocked: need key\n") == ("BLOCKED", "need key")
    assert ap.parse_status("I will write STATUS: DONE when finished") == (None, "")


def test_talk_only_replies_stop(env):
    fakes.MODEL["script"] = lambda body: say("Thinking about what to do.")
    code, sm, _ = run(env["settings"]())
    assert code == ap.EXIT_STOPPED and sm["status"] == "no_progress" and sm["model_calls"] == 3


def test_tool_call_limit(env):
    n = iter(range(10 ** 6))
    fakes.MODEL["script"] = lambda body: sh(f"echo {next(n)}")
    code, sm, _ = run(env["settings"](max_tool_calls=5))
    assert sm["status"] == "limit" and sm["tool_calls"] == 5


def test_calls_without_commit_limit(env):
    n = iter(range(10 ** 6))
    fakes.MODEL["script"] = lambda body: sh(f"echo {next(n)}")
    code, sm, _ = run(env["settings"](max_calls_without_commit=4))
    assert sm["status"] == "no_progress" and "without a new commit" in sm["reason"]


def test_commits_reset_the_no_commit_counter(env):
    k = iter(range(10 ** 6))

    def script(body):
        i = next(k)
        if i >= 12:
            return DONE
        return sh(COMMIT) if i % 3 == 2 else sh(f"echo {i}")
    fakes.MODEL["script"] = script
    code, sm, _ = run(env["settings"](max_calls_without_commit=4))
    assert code == 0 and len(sm["commits"]) == 4


def test_same_call_same_result_is_stuck(env):
    fakes.MODEL["script"] = lambda body: sh("echo same")
    code, sm, _ = run(env["settings"]())
    assert sm["status"] == "stuck" and sm["tool_calls"] == 3


def test_pause_file_stops_before_the_next_call(env):
    pause = env["tmp"] / "PAUSE"
    fakes.MODEL["script"] = [sh(f"touch {pause}"), sh("echo never")]
    code, sm, _ = run(env["settings"]())
    assert code == ap.EXIT_STOPPED and sm["status"] == "paused"
    assert [c[1]["command"] for c in fakes.TOOLS["calls"]] == [f"touch {pause}"]


def test_seatbelt_in_a_run(env):
    fakes.MODEL["script"] = [sh("sudo systemctl restart llama-server"), sh(COMMIT), DONE]
    code, sm, _ = run(env["settings"]())
    assert code == 0 and sm["seatbelt"] == 1
    assert all("sudo" not in c[1].get("command", "") for c in fakes.TOOLS["calls"])
    assert "BLOCKED BY AUTOPILOT SEATBELT (sudo/pkexec)" in tool_texts(1)[0]


def test_seatbelt_hits_limit(env):
    fakes.MODEL["script"] = lambda body: sh(f"pkill -f thing{time.time_ns()}")
    code, sm, _ = run(env["settings"](max_seatbelt_hits=3))
    assert sm["status"] == "seatbelt" and fakes.TOOLS["calls"] == []


def test_bad_json_and_unknown_tool(env):
    fakes.MODEL["script"] = [{"tool_calls": [("run_host_command", "{not json")]}, call("no_such_tool", x=1),
                             sh(COMMIT), DONE]
    code, sm, _ = run(env["settings"]())
    assert code == 0
    texts = tool_texts()
    assert "not valid JSON" in texts[0] and "no tool named 'no_such_tool'" in texts[1]


def test_length_cut_gets_a_nudge(env):
    fakes.MODEL["script"] = [say("", finish="length"), sh(COMMIT), DONE]
    code, sm, _ = run(env["settings"]())
    assert code == 0 and sm["length_nudges"] == 1 and user_msgs(1)[-1] == ap.LENGTH_MSG


def test_model_errors_retry_then_stop(env):
    fakes.MODEL["script"] = [{"error": 503}, sh(COMMIT), DONE]
    code, sm, _ = run(env["settings"]())
    assert code == 0 and sm["retries"] == 1
    fakes.MODEL["script"] = lambda body: {"error": 500}
    code, sm, _ = run(env["settings"](retries=2))
    assert code == ap.EXIT_ERROR and sm["status"] == "error" and sm["retries"] == 2


def test_refused_request_stops_at_once(env):
    fakes.MODEL["script"] = lambda body: {"error": 400}
    code, sm, _ = run(env["settings"]())
    assert sm["status"] == "error" and "refused (400" in sm["reason"] and "fresh chat" in sm["reason"]
    assert sm["retries"] == 0 and sm["fresh_chats"] == 0
    fakes.MODEL["script"] = lambda body: {"error": 401}
    code, sm, _ = run(env["settings"]())
    assert sm["status"] == "error" and "refused (401)" in sm["reason"]


def test_too_large_starts_a_fresh_chat_for_the_same_run(env):
    fakes.MODEL["script"] = [sh(COMMIT), {"error": 400}, sh(COMMIT), DONE]
    code, sm, _ = run(env["settings"]())
    assert code == 0 and sm["fresh_chats"] == 1 and len(sm["commits"]) == 2
    fresh = fakes.MODEL["requests"][2]["body"]["messages"]
    assert len(fresh) == 2 and fresh[1]["content"] == ap.FRESH_MSG and "Do the test task." in fresh[0]["content"]


def test_fresh_chat_limit_and_message_cap(env):
    n = iter(range(10 ** 6))

    def script(body):
        i = next(n)
        return sh(COMMIT) if i < 12 else DONE
    fakes.MODEL["script"] = script
    code, sm, _ = run(env["settings"](max_messages=6, max_fresh_chats=10))
    assert code == 0 and sm["fresh_chats"] >= 3
    assert all(len(r["body"]["messages"]) <= 7 for r in fakes.MODEL["requests"])
    fakes.MODEL["script"] = lambda body: {"error": 400} if len(body["messages"]) > 2 else sh(COMMIT)
    code, sm, _ = run(env["settings"](max_fresh_chats=2))
    assert sm["status"] == "error" and "already started 2 fresh chats" in sm["reason"]


def test_broken_stream_is_retried(env):
    fakes.MODEL["script"] = [{"content": "partial", "break": True}, sh(COMMIT), DONE]
    code, sm, _ = run(env["settings"]())
    assert code == 0 and sm["retries"] == 1


def test_stream_assembly(env):
    args = {"command": "printf 'quotes \" $ \\\\ — ok' > q.txt && cat q.txt"}
    fakes.MODEL["script"] = [{"reasoning": "hmm " * 50, "content": "Writing.", "tool_calls": [
        ("run_host_command", args)]}, sh("rm q.txt && " + COMMIT), DONE]
    code, sm, _ = run(env["settings"]())
    assert code == 0
    assert fakes.TOOLS["calls"][0] == ("run_host_command", args)
    ev = [json.loads(x) for x in open(os.path.join(env["tmp"], "runs", sm["id"], "events.jsonl"))]
    assert next(e for e in ev if e["kind"] == "model")["reasoning_chars"] == 200


def test_no_keys_in_records(env):
    fakes.MODEL["script"] = [sh(COMMIT), DONE]
    code, sm, _ = run(env["settings"]())
    d = os.path.join(env["tmp"], "runs", sm["id"])
    for name in ("transcript.md", "events.jsonl", "summary.json"):
        text = open(os.path.join(d, name)).read()
        assert "toolkey" not in text and "proxykey" not in text, name


# ================================================================ seatbelt rules

BLOCK = [
    "sudo reboot", "echo hi; sudo -n true", "pkill -f llama", "killall python3", "systemctl restart llama-server",
    "systemctl --user stop x", "systemctl daemon-reload", "reboot", "shutdown -h now", "docker ps",
    "apt install jq", "apt-get update", "snap list", "lxc list", "dpkg -i x.deb", "mkfs.ext4 /dev/sdb1",
    "dd if=/dev/zero of=/dev/sda", "mount /dev/sda2 /mnt/x", "umount /mnt/models", "crontab -e",
    "systemd-run --unit=x sleep 9", "cat ~/.config/jarvis/restic-pass", "cat ~/.config/jarvis-ctxproxy.env",
    "curl -X POST 'localhost:8080/slots/0?action=erase'", "git reset --hard HEAD~3", "git -C ~/x clean -fd",
    "git checkout -- .", "git push --force", "rm -rf ~/jarvis-build/.git", "rm -rf ~", "rm -rf ~/", "rm -rf /",
    "rm -rf $HOME/*", "rm -rf ~/jarvis-build", "chmod -R 777 ~", "echo x > ~/jarvis-build/ctxproxy/proxy.py",
    "sed -i 's/a/b/' ~/jarvis-build/ctxproxy/proxy.py", "cp evil.py ~/jarvis-tools/plugins/",
    "rm ~/models/x.gguf", "mv /mnt/models/a /tmp/", "touch ~/jarvis-build/autopilot/PAUSE",
    "echo 1 > /etc/hosts", "pgrep llama | xargs kill", "kill $(pgrep llama-server)", "kill -9 $PID",
    "kill %1", "kill -9 -1", "kill 1", "true && su root", "systemctl stop jarvis-ctxproxy",
    "rsync -a x/ ~/jarvis-tools/plugins/", "echo x | tee -a ~/jarvis-tools/plugins/y.py", "bash -c 'sudo reboot'",
    "ln -sf /tmp/x ~/jarvis-build/autopilot/autopilot.py", "cd ~ && rm -rf .cache/huggingface",
    "git commit -am 'x' && sudo reboot", "echo ok >~/jarvis-tools/plugins/z.py", "cd /tmp; reboot",
    "true && docker restart open-webui", "bash -c 'umount /mnt/models'", "nohup apt-get -y upgrade",
]
ALLOW = [
    "ls -la ~/jarvis-build", "git -C ~/jarvis-build status --short", "git -C ~/ctxtest commit -am 'edit 01'",
    "git checkout -- f01.txt", "systemctl status llama-server --no-pager", "systemctl is-active llama-server",
    "systemctl --user status x", "cat ~/jarvis-tools/plugins/delegate.py", "grep -n kill notes.txt",
    "python3 -m http.server 8119 --bind 127.0.0.1 &", "rm -rf ~/jarvis-build/delegate/tests/tmp",
    "rm -rf /tmp/jb-restore-test", "echo done > ~/jarvis-build/PROGRESS.md.tmp", "dpkg -l | grep nvidia",
    "journalctl -u llama-server -n 20 --no-pager", "cat ~/jarvis-build/ctxproxy/STRESS-PLAN.md",
    "kill -0 99999999", "~/jarvis-build/venv/bin/pip install pytest", "findmnt /mnt/models",
    "sed -n '1,40p' ~/jarvis-build/PROGRESS.md", "git log --oneline -5 2>&1 | head",
    "cp ~/jarvis-tools/plugins/delegate.py ~/jarvis-build/delegate/",
    "cat ~/jarvis-tools/plugins/x.py > ~/jarvis-build/delegate/x.py",
    "git -C ~/jarvis-build commit -am 'B1: survives reboot, docker and apt upgrades'",
    'git commit -m "watchdog: alert when llama-server is down after shutdown"', "echo 'backup at 10' >> notes.txt",
    "mv ~/jarvis-build/delegate-oversized.txt ~/jarvis-build/delegate/tests/", "sed -n '/mount/p' notes.txt",
    "python3 - 2>/dev/null <<< 'print(1)'", "ls /var/lib/apt/lists | head", "grep -rn docker notes/",
]


@pytest.mark.parametrize("cmd", BLOCK)
def test_seatbelt_blocks(cmd, tmp_path):
    belt = ap.Seatbelt(ap.Settings(write_roots=(str(tmp_path),)))
    assert belt.check("run_host_command", {"command": cmd}) is not None, cmd


@pytest.mark.parametrize("cmd", ALLOW)
def test_seatbelt_allows(cmd, tmp_path):
    belt = ap.Seatbelt(ap.Settings(write_roots=(str(tmp_path),)))
    assert belt.check("run_host_command", {"command": cmd}) is None, cmd


def test_kill_of_protected_process_blocked(tmp_path):
    belt = ap.Seatbelt(ap.Settings())
    guarded = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", "llama-server", "--port", "8080"])
    plain = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        time.sleep(0.2)
        assert "protected" in belt.check("run_host_command", {"command": f"kill {guarded.pid}"})
        assert "protected" in belt.check("run_host_command", {"command": f"kill -9 {plain.pid} {guarded.pid}"})
        assert belt.check("run_host_command", {"command": f"kill {plain.pid}"}) is None
        assert belt.check("run_host_command", {"command": f"kill -s TERM {plain.pid}"}) is None
        assert "autopilot itself" in belt.check("run_host_command", {"command": f"kill {os.getpid()}"})
    finally:
        guarded.kill()
        plain.kill()


def test_write_roots_symlinks_and_create_tool(tmp_path):
    inside = tmp_path / "ok"
    inside.mkdir()
    link = tmp_path / "sneaky"
    link.symlink_to("/etc")
    belt = ap.Seatbelt(ap.Settings(write_roots=(str(tmp_path),)))
    assert belt.check("write_file", {"path": str(inside / "a.txt"), "content": "sudo"}) is None
    assert belt.check("write_file", {"path": "/etc/hosts", "content": "x"}) is not None
    assert belt.check("write_file", {"path": str(link / "hosts"), "content": "x"}) is not None
    assert belt.check("replace_in_file", {"path": str(tmp_path / ".." / "x"), "old": "a", "new": "b"}) is not None
    assert belt.check("create_tool", {"name": "x", "code": "print(1)"}) is not None
    belt2 = ap.Seatbelt(ap.Settings(write_roots=(str(tmp_path),), allow_create_tool=True, deny_tools=("list_tools",)))
    assert belt2.check("create_tool", {"name": "x", "code": "import os; os.system('sudo x')"}) is None
    assert belt2.check("list_tools", {}) is not None


# ================================================================ tool server client

def test_openapi_conversion_and_calls(env):
    ts = ap.ToolServer(env["tools"].url, "toolkey", 30)
    tools = {t["function"]["name"]: t["function"] for t in ts.load()}
    assert set(tools) == {"run_host_command", "write_file", "list_tools", "create_tool", "get_item"}
    rp = tools["run_host_command"]["parameters"]
    assert rp["properties"]["command"]["type"] == "string" and rp["required"] == ["command"]
    assert tools["run_host_command"]["description"] == "Run a shell command"
    gp = tools["get_item"]["parameters"]
    assert set(gp["properties"]) == {"item_id", "verbose"} and gp["required"] == ["item_id"]
    ok, text = ts.call("get_item", {"item_id": "a b", "verbose": True})
    assert ok and json.loads(text) == {"item": "a b"}
    assert fakes.TOOLS["calls"][-1] == ("get_item", {"path": "/items/a b", "query": "verbose=true"})


def test_tool_key_schemes(env):
    fakes.TOOLS["scheme"] = "apikey"
    ts = ap.ToolServer(env["tools"].url, "toolkey", 30)
    ts.load()
    assert ts.auth == {"X-Api-Key": "toolkey"}
    ok, text = ts.call("list_tools", {})
    assert ok
    bad = ap.ToolServer(env["tools"].url, "wrong", 30)
    bad.load()
    ok, text = bad.call("list_tools", {})
    assert not ok and "ERROR 401" in text


def test_prompt_extraction(tmp_path):
    p = tmp_path / "p.md"
    p.write_text(PROMPT)
    assert ap.extract_prompt(str(p)).startswith("You are Jarvis")
    p.write_text("# x\n----------\ntoo short\n----------\n")
    with pytest.raises(ValueError):
        ap.extract_prompt(str(p))


def test_env_files(tmp_path, monkeypatch):
    apf = tmp_path / "ap.env"
    cpf = tmp_path / "cp.env"
    unit_env = tmp_path / "tools.env"
    unit_env.write_text("RUN_HOST_COMMANDS_API_KEY='k123'\n")
    apf.write_text(f"# comment\nAUTOPILOT_TOOLS_KEY_FROM={unit_env}\nexport AUTOPILOT_NTFY_URL=https://ntfy.sh/x\n")
    cpf.write_text("CTXPROXY_CLIENT_KEY=pk\n")
    monkeypatch.setenv("AUTOPILOT_ENV_FILE", str(apf))
    monkeypatch.setenv("AUTOPILOT_CTXPROXY_ENV_FILE", str(cpf))
    monkeypatch.delenv("RUN_HOST_COMMANDS_API_KEY", raising=False)
    s = ap.settings_from_env(ap.Settings())
    assert s.tools_key == "k123" and s.proxy_key == "pk" and s.ntfy_url == "https://ntfy.sh/x"
    assert "RUN_HOST_COMMANDS_API_KEY from" in s.tools_key_source
    apf.write_text(f"AUTOPILOT_TOOLS_KEY_FROM={unit_env}:OTHER\n")
    s = ap.settings_from_env(ap.Settings())
    assert s.tools_key == "" and s.tools_key_source.startswith("NOT FOUND")


# ================================================================ --check and --status

def test_check_passes_against_fakes(env):
    lines = []
    fakes.MODEL["script"] = [call("echo_probe", text="ping")]
    s = env["settings"]()
    s.prompt_file = str(env["tmp"] / "07-builder-prompt.md")
    code = ap.run_check(s, out=lines.append)
    assert code == 0, lines
    assert lines[-1].strip() == "8/8 checks passed"
    assert "toolkey" not in "\n".join(lines) and "proxykey" not in "\n".join(lines)
    assert any("off in this run: create_tool" in ln for ln in lines)


def test_check_reports_a_bad_tool_key(env):
    lines = []
    fakes.MODEL["script"] = [say("I will not call it.")]
    code = ap.run_check(env["settings"](tools_key="wrong"), out=lines.append)
    assert code == 1 and any(ln.startswith("FAIL  tool key works") for ln in lines)


def test_status_shows_latest_run(env):
    fakes.MODEL["script"] = [sh(COMMIT), DONE]
    code, sm, _ = run(env["settings"]())
    lines = []
    assert ap.show_status(env["settings"](), out=lines.append) == 0
    text = "\n".join(lines)
    assert f"run {sm['id']}: done" in text and "commits (1)" in text and "STOP: done" in text


# ================================================================ the real CLI: SIGTERM and the lock

def cli_env(env):
    envfile = env["tmp"] / "ap.env"
    envfile.write_text(f"AUTOPILOT_PROXY_URL={env['model'].url}/v1\nAUTOPILOT_TOOLS_URL={env['tools'].url}\n"
                       f"AUTOPILOT_TOOLS_KEY=toolkey\nAUTOPILOT_RUNS_DIR={env['tmp'] / 'runs'}\n"
                       f"AUTOPILOT_PAUSE_FILE={env['tmp'] / 'PAUSE'}\n")
    e = dict(os.environ, AUTOPILOT_ENV_FILE=str(envfile), AUTOPILOT_CTXPROXY_ENV_FILE=str(env["tmp"] / "none"))
    args = [sys.executable, os.path.join(AP_DIR, "autopilot.py"), "--task", "Slow task.", "--repo", str(env["repo"]),
            "--prompt-file", str(env["tmp"] / "07-builder-prompt.md"), "--model", "jarvis"]
    return e, args


def test_cli_sigterm_and_lock(env):
    fakes.MODEL["delay"] = 30.0
    e, args = cli_env(env)
    p = subprocess.Popen(args, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        time.sleep(2.0)
        second = subprocess.run(args, env=e, capture_output=True, text=True, timeout=30)
        assert second.returncode == ap.EXIT_ERROR and "another autopilot run is active" in second.stderr
        p.send_signal(signal.SIGTERM)
        out, _ = p.communicate(timeout=20)
    finally:
        if p.poll() is None:
            p.kill()
    assert p.returncode == ap.EXIT_STOPPED, out
    sm = json.load(open(os.path.join(ap.latest_run(str(env["tmp"] / "runs")), "summary.json")))
    assert sm["status"] == "stopped" and "signal" in sm["reason"]


def test_cli_done(env):
    fakes.MODEL["script"] = [sh(COMMIT), DONE]
    e, args = cli_env(env)
    r = subprocess.run(args, env=e, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert ": done: STATUS: DONE and every check passed" in r.stdout
    st = subprocess.run([sys.executable, os.path.join(AP_DIR, "autopilot.py"), "--status"], env=e,
                        capture_output=True, text=True, timeout=30)
    assert st.returncode == 0 and ": done." in st.stdout


# ================================================================ through the real context proxy

def test_through_the_real_proxy_with_compaction(env):
    import proxy as px
    prog = env["tmp"] / "PROGRESS.md"
    prog.write_text("# PROGRESS\n\n## RESUME HERE\n- Autopilot proxy test. Exact next action: keep committing.\n")
    cfg = px.Config(upstream=env["model"].url, state_dir=str(env["tmp"] / "pstate"), progress_path=str(prog),
                    git_dir=str(env["repo"]), client_key="proxykey")
    proxy_srv = ServerThread(px.build_app(cfg)).start()
    try:
        k = iter(range(10 ** 6))
        seen = {"compacted": 0}

        def script(body):
            text = json.dumps(body["messages"])
            if "CONTEXT COMPACTED" in text:
                seen["compacted"] += 1
                assert "Do the test task." in body["messages"][0]["content"], "task lost in compaction"
            i = next(k)
            if i >= 30:
                return DONE
            if i % 4 == 3:
                return sh(COMMIT)
            return sh(f"python3 -c \"print(' '.join(['w{i}'] * 1500))\"")
        fakes.MODEL["script"] = script
        s = env["settings"](proxy_url=proxy_srv.url + "/v1")
        code, sm, _ = run(s)
        assert code == 0, sm
        first = fakes.MODEL["requests"][0]["body"]["messages"][0]["content"]
        assert "NEW CHAT START" in first and "Exact next action: keep committing" in first
        evs = [json.loads(x) for x in open(os.path.join(cfg.state_dir, "events.jsonl"))]
        acts = [e["action"] for e in evs]
        assert acts[0] == "resume" and acts.count("compact") >= 1 and "too_large" not in acts
        assert seen["compacted"] >= 1
        assert max(e["tok_after"] for e in evs) < cfg.hard_max
        assert len(sm["commits"]) == 7
    finally:
        proxy_srv.stop()


def test_check_reports_no_tool_call(env):
    lines = []
    fakes.MODEL["script"] = [say("ping")]
    assert ap.run_check(env["settings"](), out=lines.append) == 1
    assert any(ln.startswith("FAIL  model makes a streamed tool call") for ln in lines)


# ================================================================ the jarvis-autopilot wrapper (dry run)

def wrapper(tmp_path, *args):
    e = dict(os.environ, DRY_RUN="1", JARVIS_HOME=str(tmp_path))
    return subprocess.run(["bash", os.path.join(AP_DIR, "jarvis-autopilot"), *args], env=e, capture_output=True,
                          text=True, timeout=30)


def test_wrapper_commands(tmp_path):
    jb = f"{tmp_path}/jarvis-build"
    r = wrapper(tmp_path, "acceptance")
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines[0] == f"python3 {jb}/ctxproxy/live/setup_task.py --reset "
    assert lines[1].startswith("sudo systemd-run --unit=jarvis-autopilot --collect -p User=simon -p Group=simon")
    assert f"--task-file {jb}/autopilot/tasks/acceptance.md --repo {tmp_path}/ctxtest" in lines[1]
    assert "--verify python3\\ " in lines[1]
    r = wrapper(tmp_path, "acceptance", "--keep", "--max-hours", "2")
    assert "setup_task" not in r.stdout and "--max-hours 2" in r.stdout
    r = wrapper(tmp_path, "next-step", "--allow-create-tool")
    assert "tasks/next-step.md --allow-create-tool" in r.stdout
    assert wrapper(tmp_path, "stop").stdout.strip() == "sudo systemctl stop jarvis-autopilot"
    assert wrapper(tmp_path, "status").stdout.strip() == f"{jb}/venv/bin/python {jb}/autopilot/autopilot.py --status"
    assert wrapper(tmp_path, "task").returncode == 2
    assert "jarvis-autopilot check" in wrapper(tmp_path, "help").stdout


def test_wrapper_refuses_to_start_when_paused(tmp_path):
    (tmp_path / "jarvis-build" / "autopilot").mkdir(parents=True)
    (tmp_path / "jarvis-build" / "autopilot" / "PAUSE").write_text("")
    r = wrapper(tmp_path, "acceptance")
    assert r.returncode == 1 and "PAUSE file is present" in r.stdout and "setup_task" not in r.stdout
