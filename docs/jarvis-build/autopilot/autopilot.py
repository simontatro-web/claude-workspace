#!/usr/bin/env python3
"""Autopilot for Jarvis Builder: runs one approved task to the end with nobody typing "continue".

It does what Open WebUI does in a Builder chat, minus the human:
- sends the chat through the context proxy, so compaction and the NEW CHAT START note work;
- runs Jarvis's tool calls against the same tool server (OpenAPI), behind a seatbelt that
  refuses the dangerous ones (sudo, pkill, systemctl stop, rm of home, killing llama-server...);
- when Jarvis ends a reply without a STATUS line, it sends "continue";
- it stops on STATUS: DONE (checked with git and an optional --verify command), STATUS: BLOCKED,
  a limit, the PAUSE file, or SIGTERM, and then notifies Simon (optional ntfy URL).

Everything a run did is in runs/<id>/: transcript.md (readable), events.jsonl (numbers), summary.json.

  autopilot.py --check                     preflight: proxy, model, tool server + key, prompt, repo
  autopilot.py --task-file F [options]     run one task (see README.md)
  autopilot.py --status                    the latest run: state, counts, last transcript lines
Exit codes: 0 done, 2 blocked, 3 stopped (limit, pause, signal), 4 error.
"""
import argparse
import dataclasses
import fcntl
import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
import urllib.parse
from collections import deque

import httpx

HOME = os.path.expanduser("~")
HERE = os.path.dirname(os.path.abspath(__file__))
EXIT_DONE, EXIT_BLOCKED, EXIT_STOPPED, EXIT_ERROR = 0, 2, 3, 4


def load_env_file(path):
    """KEY=VALUE lines (comments, blank lines, 'export ' and quotes allowed). Missing file -> {}."""
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                if k.startswith("export "):
                    k = k[7:].strip()
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                out[k] = v
    except (FileNotFoundError, PermissionError):
        pass
    return out


@dataclasses.dataclass
class Settings:
    proxy_url: str = "http://172.17.0.1:8090/v1"
    proxy_key: str = ""
    tools_url: str = "http://127.0.0.1:8200"
    tools_key: str = ""
    tools_key_source: str = "none"
    ntfy_url: str = ""
    model: str = ""
    prompt_file: str = HOME + "/jarvis-build/handoff/07-builder-prompt.md"
    task: str = ""
    task_name: str = ""
    repo: str = HOME + "/jarvis-build"
    verify: str = ""
    verify_timeout_s: float = 600.0
    require_commit: bool = True
    require_clean: bool = True
    write_roots: tuple = (HOME + "/jarvis-build", HOME + "/ctxtest", "/tmp")
    allow_create_tool: bool = False
    deny_tools: tuple = ()
    max_hours: float = 4.0
    max_model_calls: int = 400
    max_tool_calls: int = 250
    max_continues: int = 40
    max_calls_without_commit: int = 60
    max_talk_turns: int = 3
    repeat_limit: int = 3
    max_seatbelt_hits: int = 8
    max_done_rejections: int = 3
    max_fresh_chats: int = 3      # a refused (too large) request starts a fresh chat for the same run
    max_messages: int = 600       # ... and so does a very long message list, before it can go wrong
    max_tokens: int = 8192
    effort: str = ""
    temperature: float = 0.0
    tool_timeout_s: float = 1200.0
    model_timeout_s: float = 900.0  # longest silence allowed between streamed chunks
    retries: int = 3
    retry_backoff_s: tuple = (5.0, 20.0, 60.0)
    max_tool_chars: int = 16000
    pause_file: str = HERE + "/PAUSE"
    runs_dir: str = HERE + "/runs"


def settings_from_env(s=None):
    """Fill keys and URLs from ~/.config/jarvis-autopilot.env and ~/.config/jarvis-ctxproxy.env."""
    s = s or Settings()
    ap = load_env_file(os.environ.get("AUTOPILOT_ENV_FILE", HOME + "/.config/jarvis-autopilot.env"))
    cp = load_env_file(os.environ.get("AUTOPILOT_CTXPROXY_ENV_FILE", HOME + "/.config/jarvis-ctxproxy.env"))

    def get(name, default=""):
        return os.environ.get(name) or ap.get(name) or default
    s.proxy_url = get("AUTOPILOT_PROXY_URL", s.proxy_url)
    s.proxy_key = get("AUTOPILOT_PROXY_KEY", cp.get("CTXPROXY_CLIENT_KEY", s.proxy_key))
    s.tools_url = get("AUTOPILOT_TOOLS_URL", s.tools_url)
    s.ntfy_url = get("AUTOPILOT_NTFY_URL", s.ntfy_url)
    s.runs_dir = get("AUTOPILOT_RUNS_DIR", s.runs_dir)
    s.pause_file = get("AUTOPILOT_PAUSE_FILE", s.pause_file)
    key = get("AUTOPILOT_TOOLS_KEY")
    if key:
        s.tools_key, s.tools_key_source = key, "AUTOPILOT_TOOLS_KEY"
    else:
        src = get("AUTOPILOT_TOOLS_KEY_FROM")  # "path" or "path:VARNAME" of an env file that holds the key
        if src:
            path, _, var = src.partition(":")
            var = var or "RUN_HOST_COMMANDS_API_KEY"
            val = load_env_file(os.path.expanduser(path)).get(var, "")
            if val:
                s.tools_key, s.tools_key_source = val, f"{var} from {path}"
            else:
                s.tools_key_source = f"NOT FOUND: {var} in {path}"
        elif os.environ.get("RUN_HOST_COMMANDS_API_KEY"):
            s.tools_key, s.tools_key_source = os.environ["RUN_HOST_COMMANDS_API_KEY"], "RUN_HOST_COMMANDS_API_KEY (environment)"
    return s


def extract_prompt(path):
    """The Builder system prompt: the text between the two ---------- lines of 07-builder-prompt.md."""
    text = open(path, encoding="utf-8").read()
    parts = re.split(r"(?m)^-{10,}[ \t]*$", text)
    body = parts[1].strip() if len(parts) >= 3 else text.strip()
    if len(body) < 200:
        raise ValueError(f"the prompt in {path} looks too short ({len(body)} chars)")
    return body


def clip(text, n):
    if len(text) <= n:
        return text
    head = int(n * 0.7)
    return text[:head] + f"\n[... {len(text) - n} chars cut by the autopilot ...]\n" + text[-(n - head):]


def short(text, n=300):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n] + "..."


# ---------------------------------------------------------------- git

def git(repo, *args, timeout=30):
    try:
        r = subprocess.run(["git", "--no-optional-locks", "-C", repo, *args], capture_output=True, text=True,
                           timeout=timeout, errors="replace", env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", type(e).__name__


def git_head(repo):
    rc, out, _ = git(repo, "rev-parse", "HEAD")
    return out if rc == 0 else None


# ---------------------------------------------------------------- seatbelt

COMMAND_KEYS = ("command", "cmd", "commands", "script", "shell", "bash")
PATH_KEYS = ("path", "file_path", "filepath", "filename", "file", "target", "dest", "destination")
WRITE_TOOL = re.compile(r"write|replace|append|edit|delete|remove|move|rename|save_file|create_file", re.I)
PROTECTED_RX = re.compile(r"(?:ctxproxy/|/autopilot|jarvis-tools|/models\b|\.cache/huggingface|/bench\b|/mnt/models|"
                          r"/etc/|\.ssh\b|\.bashrc|\.profile|/usr/|/var/|/boot/)")
DEST_ONLY = {"cp", "rsync", "install", "ln", "scp"}          # only the last path is written
ALL_TARGETS = {"rm", "rmdir", "unlink", "shred", "truncate", "touch", "mkdir", "chmod", "chown", "tee", "mv", "sed",
               "perl", "dd"}
COMMIT_MSG = re.compile(r"""(\bgit\b[^;&|\n]*?\s(?:-a?m|--message=?))\s*("[^"]*"|'[^']*'|\S+)""")
CMD_POS = r"(?:^|[;&|(`'\"]|\$\(|\bthen\s|\bdo\s|\bexec\s|\bsudo\s|\bxargs\s|\bnohup\s|\btimeout\s+\S+\s)\s*"
RULES = [(re.compile(p), why) for p, why in [
    (r"\bsudo\b|\bdoas\b|\bpkexec\b", "sudo/pkexec"),
    (r"(?:^|[;&|(]\s*|\bexec\s+)su(?:\s|$)", "su"),
    (r"\b(?:pkill|killall)\b", "pkill/killall"),
    (CMD_POS + r"(?:reboot|shutdown|poweroff|halt|telinit)\b", "reboot/shutdown"),
    (CMD_POS + r"(?:docker|podman|nerdctl)\b", "docker"),
    (CMD_POS + r"(?:apt|apt-get|aptitude|snap|lxc|lxd)\b", "apt/snap/lxc/lxd"),
    (r"\bdpkg\s+(?:-i|--install|-r|--remove|-P|--purge|--configure|--unpack)\b", "dpkg changes"),
    (r"\b(?:mkfs(?:\.\w+)?|wipefs|fdisk|sfdisk|parted|sgdisk|mkswap|swapoff|swapon)\b|\bdd\b[^;&|\n]*\bof=",
     "disk tools"),
    (CMD_POS + r"(?:mount|umount)\b", "mount/umount"),
    (r"\bcrontab\b|\bsystemd-run\b", "scheduling jobs"),
    (r"\.config/jarvis", "~/.config/jarvis* (keys)"),
    (r"\bjarvis-(?:autopilot|ctxproxy)\b", "the autopilot or proxy service"),
    (r"/slots(?:/\d+)?\?action=", "llama-server slot actions"),
    (r"\bgit\b[^;&|\n]*\s(?:reset\s+--hard|clean\s+-\w*[fdx]|push\s+(?:-f\b|--force)|checkout\s+(?:--\s+)?\.(?:\s|$)"
     r"|restore\s+(?:--\S+\s+)*\.(?:\s|$)|branch\s+-D|filter-branch|reflog\s+expire|update-ref\s+-d"
     r"|stash\s+(?:drop|clear))", "a git command that destroys work"),
    (r"\brm\b[^;&|\n]*\.git(?:/|\s|$)", "deleting a git repository"),
    (r"\brm\s+(?:-\S+\s+)*[\"']?(?:/|~|\$HOME|/home/simon|/home)/?[\"']?(?:\s|$|\*)", "rm of / or a home directory"),
    (r"\brm\s+(?:-\S+\s+)*[^;&|\n]*jarvis-build/?[\"']?(?:\s|$)", "rm of ~/jarvis-build itself"),
    (r"\b(?:chmod|chown)\s+-R\b[^;&|\n]*(?:~|/home/simon|\$HOME)/?(?:\s|$)", "recursive chmod/chown of home"),
    (r"\bsystemctl\b(?!\s+(?:--user\s+|--no-pager\s+|-l\s+|--full\s+)*(?:status|is-active|is-enabled|is-failed|"
     r"show|cat|list-units|list-timers|list-unit-files|list-dependencies)\b)(?=\s+\S)",
     "systemctl other than status/show/cat/list"),
    (r"\bxargs\b[^;&|\n]*\bkill\b", "kill through xargs"),
]]
KILL_AT = re.compile(r"(?:^|[;&|(`]|\$\(|\bthen\b|\bdo\b|\bexec\b|\btimeout\s+\S+)\s*kill\b([^;&|\n)`]*)")
PROTECTED_PROCS = ("llama-server", "llama_server", "main:app", "--port 8200", "--port 8080", "--port 8090",
                   "proxy.py", "autopilot.py", "open-webui", "open_webui", "dockerd", "containerd", "sshd",
                   "tailscaled", "/sbin/init", "systemd", "restic")
SEATBELT_MSG = ("BLOCKED BY AUTOPILOT SEATBELT ({why}). Nothing was run. This needs Simon: do something else, "
                "or end your reply with STATUS: BLOCKED: <what you need>. Do not try to get around it.")


def protected_pid(pid):
    if pid in (os.getpid(), os.getppid()):
        return f"PID {pid} is the autopilot itself"
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace")
    except OSError:
        return None  # no such process: kill will fail on its own
    for p in PROTECTED_PROCS:
        if p in cmd:
            return f"PID {pid} is protected ({p})"
    return None


def write_targets(cmd):
    """Paths a shell command would write: redirect targets, and the targets of common file verbs."""
    targets = [m.group(1) for m in re.finditer(r">>?\s*([^\s;&|<>]+)", cmd) if not m.group(1).startswith("&")]
    for part in re.split(r"&&|\|\||[;&|\n]", cmd):
        try:
            toks = shlex.split(part)
        except ValueError:
            toks = part.split()
        while toks and (re.match(r"^\w+=", toks[0]) or toks[0] in ("env", "nice", "nohup", "time", "command",
                                                                  "exec", "xargs", "timeout")):
            toks = toks[2:] if toks[0] == "timeout" else toks[1:]
        if not toks:
            continue
        verb = os.path.basename(toks[0])
        opts = [t for t in toks[1:] if t.startswith("-")]
        args = [t for t in toks[1:] if not t.startswith("-")]
        if verb in DEST_ONLY and args:
            targets.append(args[-1])
        elif verb in ALL_TARGETS:
            if verb == "sed" and not any(o.startswith("-i") or o.startswith("--in-place") for o in opts):
                continue
            if verb == "perl" and not any(re.match(r"-\w*i", o) for o in opts):
                continue
            if verb in ("chmod", "chown"):
                args = args[1:]
            if verb == "dd":
                args = [t[3:] for t in toks[1:] if t.startswith("of=")]
            targets += args
    return targets


def check_kill(cmd):
    for m in KILL_AT.finditer(cmd):
        toks = m.group(1).split()
        if not toks or toks[0] in ("-l", "-L", "--list"):
            continue
        i = 2 if toks[0] in ("-s", "-n", "--signal") else (1 if toks[0].startswith("-") else 0)
        for t in toks[i:]:
            if t == "--":
                continue
            if not t.isdigit():
                return f"kill needs literal PIDs of processes you started (got {t!r})"
            if int(t) <= 1:
                return "kill of PID 0 or 1"
            why = protected_pid(int(t))
            if why:
                return why
    return None


class Seatbelt:
    """Refuses clearly dangerous tool calls. A seatbelt against accidents, not a security boundary."""

    def __init__(self, s):
        self.allow_create_tool = s.allow_create_tool
        self.deny = set(s.deny_tools)
        self.roots = [os.path.realpath(os.path.expanduser(r)) for r in s.write_roots]

    def check(self, name, args):
        if name in self.deny:
            return f"tool {name} is turned off for this run"
        if "create_tool" in name and not self.allow_create_tool:
            return "create_tool is only allowed in runs started with --allow-create-tool"
        for k in COMMAND_KEYS:
            v = args.get(k)
            if isinstance(v, list):
                v = "\n".join(str(x) for x in v)
            if isinstance(v, str):
                scan = COMMIT_MSG.sub(r"\1 MSG", v)  # words in a commit message are not commands
                for rx, why in RULES:
                    if rx.search(scan):
                        return why
                why = check_kill(scan)
                if why:
                    return why
                for t in write_targets(scan):
                    if PROTECTED_RX.search(t):
                        return f"writing to a protected path ({t})"
        if WRITE_TOOL.search(name):
            for k in PATH_KEYS:
                v = args.get(k)
                if isinstance(v, str) and v:
                    real = os.path.realpath(os.path.expanduser(v))
                    if not any(real == r or real.startswith(r + os.sep) for r in self.roots):
                        return f"{name} outside the allowed folders ({', '.join(self.roots)})"
        return None


# ---------------------------------------------------------------- tool server (OpenAPI, like Open WebUI)

class ToolServer:
    def __init__(self, base, key, timeout_s, client=None):
        self.base = base.rstrip("/")
        self.key = key
        self.timeout_s = timeout_s
        self.client = client or httpx.Client()
        self.ops = {}
        self.spec = {}
        self.prefix = ""
        self.auth = {"Authorization": "Bearer " + key} if key else {}

    def resolve(self, node, hops=0):
        if isinstance(node, dict):
            if "$ref" in node:
                if hops > 10 or not str(node["$ref"]).startswith("#/"):
                    return {}
                tgt = self.spec
                for part in node["$ref"][2:].split("/"):
                    tgt = tgt.get(part, {}) if isinstance(tgt, dict) else {}
                merged = dict(self.resolve(tgt, hops + 1))
                merged.update({k: self.resolve(v, hops) for k, v in node.items() if k != "$ref"})
                return merged
            return {k: self.resolve(v, hops) for k, v in node.items()}
        if isinstance(node, list):
            return [self.resolve(x, hops) for x in node]
        return node

    def load(self):
        r = self.client.get(self.base + "/openapi.json", headers=self.auth, timeout=30)
        r.raise_for_status()
        self.spec = spec = r.json()
        servers = spec.get("servers") or []
        if servers and isinstance(servers[0], dict) and str(servers[0].get("url", "")).startswith("/"):
            self.prefix = servers[0]["url"].rstrip("/")
        if self.key:
            for sch in ((spec.get("components") or {}).get("securitySchemes") or {}).values():
                if sch.get("type") == "apiKey" and sch.get("in") == "header" and sch.get("name"):
                    self.auth = {sch["name"]: self.key}
                    break
        tools = []
        for path, item in (spec.get("paths") or {}).items():
            for method, op in item.items():
                if method.lower() not in ("get", "post", "put", "patch", "delete") or not isinstance(op, dict):
                    continue
                if not op.get("operationId"):
                    continue
                name = re.sub(r"[^A-Za-z0-9_-]", "_", op["operationId"])[:64]
                props, required, locs = {}, [], {}
                for prm in list(item.get("parameters") or []) + list(op.get("parameters") or []):
                    prm = self.resolve(prm)
                    if prm.get("in") not in ("query", "path") or not prm.get("name"):
                        continue
                    sch = dict(self.resolve(prm.get("schema") or {"type": "string"}))
                    if prm.get("description"):
                        sch["description"] = prm["description"]
                    props[prm["name"]] = sch
                    locs[prm["name"]] = prm["in"]
                    if prm.get("required") or prm.get("in") == "path":
                        required.append(prm["name"])
                content = ((op.get("requestBody") or {}).get("content") or {}).get("application/json")
                if content:
                    bs = self.resolve(content.get("schema") or {})
                    if bs.get("type") == "object" or "properties" in bs:
                        for k, v in (bs.get("properties") or {}).items():
                            props[k] = v
                            locs[k] = "body"
                        required += [k for k in (bs.get("required") or []) if k not in required]
                    else:
                        props["body"] = bs
                        locs["body"] = "rawbody"
                        required.append("body")
                params = {"type": "object", "properties": props}
                if required:
                    params["required"] = required
                desc = str(op.get("description") or op.get("summary") or name).strip()[:1024]
                tools.append({"type": "function", "function": {"name": name, "description": desc,
                                                               "parameters": params}})
                self.ops[name] = (method.upper(), path, locs)
        return tools

    def call(self, name, args):
        """(ok, text). Never raises for HTTP problems; they come back as text for Jarvis to read."""
        method, path, locs = self.ops[name]
        query, body = {}, {}
        for k, v in args.items():
            loc = locs.get(k, "body")
            if loc == "path":
                path = path.replace("{" + k + "}", urllib.parse.quote(str(v), safe=""))
            elif loc == "query":
                query[k] = v
            elif loc == "rawbody":
                body = v
            else:
                body[k] = v
        kw = {"headers": self.auth, "timeout": httpx.Timeout(self.timeout_s, connect=10.0)}
        if query:
            kw["params"] = query
        if method in ("POST", "PUT", "PATCH"):
            kw["json"] = body
        try:
            r = self.client.request(method, self.base + self.prefix + path, **kw)
        except httpx.HTTPError as e:
            return False, f"ERROR: the tool server did not answer ({type(e).__name__})"
        try:
            data = r.json()
            text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
        except ValueError:
            text = r.text
        if r.status_code >= 400:
            return False, f"ERROR {r.status_code} from the tool server: {text[:3000]}"
        return True, text


# ---------------------------------------------------------------- model (through the context proxy)

class ModelError(Exception):
    def __init__(self, status, text):
        super().__init__(f"{status}: {text}")
        self.status = status
        self.text = text


class Model:
    def __init__(self, s, client=None):
        self.s = s
        self.url = s.proxy_url.rstrip("/")
        self.client = client or httpx.Client(timeout=httpx.Timeout(s.model_timeout_s, connect=10.0))

    def headers(self, extra=None):
        h = {"Content-Type": "application/json"}
        if self.s.proxy_key:
            h["Authorization"] = "Bearer " + self.s.proxy_key
        h.update(extra or {})
        return h

    def models(self):
        r = self.client.get(self.url + "/models", headers=self.headers(), timeout=30)
        if r.status_code != 200:
            raise ModelError(r.status_code, r.text[:300])
        return [m.get("id") for m in r.json().get("data", [])]

    def ping(self, model):
        body = {"model": model, "messages": [{"role": "user", "content": "Reply with the word OK."}],
                "max_tokens": 16, "temperature": 0, "stream": False,
                "chat_template_kwargs": {"enable_thinking": False}}
        r = self.client.post(self.url + "/chat/completions", json=body,
                             headers=self.headers({"X-Ctxproxy-No-Resume": "1"}), timeout=120)
        if r.status_code != 200:
            raise ModelError(r.status_code, r.text[:300])
        return (r.json()["choices"][0]["message"].get("content") or "").strip()

    def chat(self, body, extra_headers=None):
        """Streamed call; returns content, tool_calls, finish_reason, reasoning_chars."""
        content, calls, finish, rchars, done = [], {}, None, 0, False
        with self.client.stream("POST", self.url + "/chat/completions", json=body,
                                headers=self.headers(extra_headers)) as r:
            if r.status_code != 200:
                raise ModelError(r.status_code, r.read().decode("utf-8", "replace")[:2000])
            for line in r.iter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    done = True
                    break
                try:
                    d = json.loads(data)
                except ValueError:
                    continue
                if d.get("error"):
                    raise ModelError(502, short(d["error"], 500))
                for ch in d.get("choices") or []:
                    delta = ch.get("delta") or {}
                    if delta.get("content"):
                        content.append(delta["content"])
                    if delta.get("reasoning_content"):
                        rchars += len(delta["reasoning_content"])
                    for tc in delta.get("tool_calls") or []:
                        cur = calls.setdefault(tc.get("index", len(calls)), {"id": None, "name": "", "arguments": ""})
                        if tc.get("id"):
                            cur["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name") and not cur["name"]:
                            cur["name"] = fn["name"]
                        if fn.get("arguments"):
                            cur["arguments"] += fn["arguments"]
                    if ch.get("finish_reason"):
                        finish = ch["finish_reason"]
        if not done and finish is None:
            raise ModelError(502, "the stream ended early")
        return "".join(content), [calls[k] for k in sorted(calls)], finish, rchars


# ---------------------------------------------------------------- the run

STATUS_RE = re.compile(r"^\s*\**\s*STATUS:\s*(DONE|BLOCKED)\b\**\s*:?\s*(.*)$", re.I | re.M)
CONTINUE_MSG = ("continue\n[AUTOPILOT: no one is watching. Keep working from your exact next action. Nobody can "
                "answer questions: decide within the task, or end with STATUS: BLOCKED: <what you need>. End with "
                "STATUS: DONE only when the task is complete, its checks pass and it is committed.]")
FRESH_MSG = ("AUTOPILOT: this is a fresh chat for the same run (the last one got too long). Your earlier messages "
             "are gone; the NEW CHAT START note in your instructions has RESUME HERE and the git facts. Run "
             "`git log --oneline -5` and `git status --short` in the repo you work in, then continue the task in "
             "your instructions.")
LENGTH_MSG = ("[AUTOPILOT: your last reply hit the length limit before you acted. Take a smaller next action "
              "and keep your thinking short.]")


class FreshChat(Exception):
    pass


class Stop(Exception):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status
        self.reason = reason


def parse_status(content):
    found = STATUS_RE.findall(content or "")
    if not found:
        return None, ""
    word, rest = found[-1]
    return word.upper(), rest.strip()


START_MSG = "AUTOPILOT: start the task in your instructions now."


def autopilot_block(s, run_id):
    """Appended to the system prompt, so the task survives every compaction (the proxy keeps system)."""
    return (f"AUTOPILOT RUN {run_id}, started {time.strftime('%Y-%m-%d %H:%M')}. No human is watching until you "
            "finish, and nobody can answer questions. Simon approved this task: do not wait for an OK. It "
            "overrides the RESUME HERE next action if they differ.\n\nTASK:\n" + s.task.strip() + "\n\n"
            "How this run works: keep making tool calls until the task is complete. When it is complete, its "
            "checks pass and everything is committed, end your reply with the line\nSTATUS: DONE\n"
            "If something outside the task blocks you (a root step, a missing key, a decision only Simon can "
            "make), end with\nSTATUS: BLOCKED: <exactly what you need>\nIf you end a reply without a STATUS "
            "line you will get \"continue\". A seatbelt refuses dangerous commands; if one is refused, do not "
            "try to get around it.")


def notify(s, title, message, priority=3):
    if not s.ntfy_url:
        return "not configured"
    try:
        r = httpx.post(s.ntfy_url, content=message.encode("utf-8"),
                       headers={"Title": title.encode("ascii", "replace").decode(), "Priority": str(priority),
                                "Tags": "robot"}, timeout=15)
        return "sent" if r.status_code < 300 else f"failed (HTTP {r.status_code})"
    except Exception as e:
        return f"failed ({type(e).__name__})"


class Run:
    def __init__(self, s, out=None, model=None, tools=None, sleep=time.sleep):
        self.s = s
        self.out = out or (lambda m: print(m, flush=True))
        self.sleep = sleep
        os.makedirs(s.runs_dir, exist_ok=True)
        base = time.strftime("%Y%m%d-%H%M%S")
        self.id, n = base, 1
        while os.path.exists(os.path.join(s.runs_dir, self.id)):
            n += 1
            self.id = f"{base}-{n}"
        self.dir = os.path.join(s.runs_dir, self.id)
        os.makedirs(self.dir)
        self.model = model or Model(s)
        self.tools = tools or ToolServer(s.tools_url, s.tools_key, s.tool_timeout_s)
        self.belt = Seatbelt(s)
        self.t0 = time.time()
        self.c = {"model_calls": 0, "tool_calls": 0, "continues": 0, "seatbelt": 0, "done_rejected": 0,
                  "retries": 0, "length_nudges": 0, "fresh_chats": 0}
        self.recent = deque(maxlen=30)
        self.last_status = ""
        self.last_reply = ""
        self.start_head = self.head = None
        self.calls_since_commit = 0
        self.talk_turns = 0

    # ---- records
    def event(self, **kw):
        with open(os.path.join(self.dir, "events.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": round(time.time(), 3), **kw}) + "\n")

    def tx(self, text):
        with open(os.path.join(self.dir, "transcript.md"), "a", encoding="utf-8") as f:
            f.write(text.rstrip("\n") + "\n\n")

    def summary(self, status, reason=""):
        rc, log, _ = git(self.s.repo, "log", "--oneline", f"{self.start_head}..HEAD") if self.start_head \
            else git(self.s.repo, "log", "--oneline", "-20")
        d = {"id": self.id, "status": status, "reason": reason, "task": self.s.task_name,
             "repo": self.s.repo, "verify": self.s.verify, "pid": os.getpid(),
             "started": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.t0)),
             "minutes": round((time.time() - self.t0) / 60, 1), **self.c,
             "commits": log.splitlines() if rc == 0 and log else [],
             "last_status_line": self.last_status, "last_reply": short(self.last_reply, 600)}
        tmp = os.path.join(self.dir, "summary.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1, ensure_ascii=False)
        os.replace(tmp, os.path.join(self.dir, "summary.json"))
        return d

    # ---- limits
    def check_limits(self):
        s, c = self.s, self.c
        if os.path.exists(s.pause_file):
            raise Stop("paused", f"PAUSE file present ({s.pause_file})")
        if time.time() - self.t0 > s.max_hours * 3600:
            raise Stop("limit", f"time limit {s.max_hours} h")
        if c["model_calls"] >= s.max_model_calls:
            raise Stop("limit", f"model call limit {s.max_model_calls}")
        if c["tool_calls"] >= s.max_tool_calls:
            raise Stop("limit", f"tool call limit {s.max_tool_calls}")
        if c["continues"] > s.max_continues:
            raise Stop("limit", f"continue limit {s.max_continues}")
        if self.calls_since_commit >= s.max_calls_without_commit:
            raise Stop("no_progress", f"{self.calls_since_commit} tool calls without a new commit in {s.repo}")
        if self.talk_turns >= s.max_talk_turns:
            raise Stop("no_progress", f"{self.talk_turns} replies in a row without any tool call")
        if c["seatbelt"] >= s.max_seatbelt_hits:
            raise Stop("seatbelt", f"{c['seatbelt']} commands refused by the seatbelt")
        if c["done_rejected"] >= s.max_done_rejections:
            raise Stop("done_rejected", f"said DONE {c['done_rejected']} times but the checks failed")

    def note_head(self):
        h = git_head(self.s.repo)
        if h != self.head:
            self.head = h
            self.calls_since_commit = 0
            self.event(kind="commit", head=(h or "")[:12])
        return h

    # ---- DONE check
    def check_done(self):
        s, problems = self.s, []
        h = git_head(s.repo)
        if s.require_commit and (h is None or h == self.start_head):
            problems.append(f"no new commit in {s.repo} since the run started")
        if s.require_clean:
            rc, out, err = git(s.repo, "status", "--porcelain")
            if rc != 0:
                problems.append(f"git status failed in {s.repo}: {err[:200]}")
            elif out:
                problems.append(f"uncommitted changes in {s.repo}:\n" + "\n".join(out.splitlines()[:10]))
        if s.verify and not problems:
            try:
                r = subprocess.run(s.verify, shell=True, capture_output=True, text=True, errors="replace",
                                   timeout=s.verify_timeout_s, cwd=s.repo if os.path.isdir(s.repo) else None)
                outp = (r.stdout + r.stderr).strip()
                self.tx("VERIFY `" + s.verify + f"` exit {r.returncode}:\n```\n{clip(outp, 3000)}\n```")
                if r.returncode != 0:
                    problems.append(f"the check `{s.verify}` failed (exit {r.returncode}):\n{clip(outp, 1500)}")
            except subprocess.TimeoutExpired:
                problems.append(f"the check `{s.verify}` timed out after {int(s.verify_timeout_s)} s")
        return problems

    # ---- one model call, with retries
    def call_model(self, body):
        waits = list(self.s.retry_backoff_s)
        for attempt in range(self.s.retries + 1):
            self.check_limits()
            t = time.time()
            try:
                res = self.model.chat(body)
                self.c["model_calls"] += 1
                return res, time.time() - t
            except ModelError as e:
                if e.status in (400, 413):  # e.g. the proxy's "too large even after compaction"
                    raise FreshChat(f"{e.status}: {short(e.text, 300)}")
                if e.status in (401, 403, 404, 422):
                    raise Stop("error", f"the model request was refused ({e.status}): {short(e.text, 400)}")
                err = f"{e.status}: {short(e.text, 200)}"
            except httpx.HTTPError as e:
                err = type(e).__name__
            self.event(kind="model_error", error=err[:200], attempt=attempt + 1)
            self.tx(f"MODEL ERROR (attempt {attempt + 1}): {err}")
            if attempt == self.s.retries:
                raise Stop("error", f"the model failed {attempt + 1} times; last error {err}")
            self.c["retries"] += 1
            self.sleep(waits[min(attempt, len(waits) - 1)])

    # ---- one tool call
    def run_tool(self, tc, n):
        name = tc["name"] or "(no name)"
        raw = tc["arguments"] or "{}"
        try:
            args = json.loads(raw)
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
        except ValueError as e:
            return name, False, f"ERROR: the tool arguments are not valid JSON ({e}). Send the call again.", False
        if name not in self.tools.ops:
            return name, False, f"ERROR: there is no tool named {name!r}.", False
        why = self.belt.check(name, args)
        if why:
            self.c["seatbelt"] += 1
            return name, False, SEATBELT_MSG.format(why=why), True
        ok, text = self.tools.call(name, args)
        return name, ok, clip(text, self.s.max_tool_chars), False

    def fresh_chat(self, why):
        """Same run, new conversation: the proxy gives it a new NEW CHAT START note."""
        if len(self.messages) <= 2:
            raise Stop("error", f"the model request was refused ({why}) even as a fresh chat")
        if self.c["fresh_chats"] >= self.s.max_fresh_chats:
            raise Stop("error", f"already started {self.c['fresh_chats']} fresh chats; last refusal: {why}")
        self.c["fresh_chats"] += 1
        self.messages = self.messages[:1] + [{"role": "user", "content": FRESH_MSG}]
        self.event(kind="fresh_chat", n=self.c["fresh_chats"])
        self.tx(f"FRESH CHAT {self.c['fresh_chats']} for the same run: {why}")

    def start(self):
        s = self.s
        self.start_head = self.head = git_head(s.repo)
        self.summary("starting")
        tools = self.tools.load()
        if not s.model:
            ids = self.model.models()
            if not ids:
                raise Stop("error", "the proxy lists no model")
            s.model = ids[0]
        system = extract_prompt(s.prompt_file) + "\n\n" + autopilot_block(s, self.id)
        self.messages = [{"role": "system", "content": system}, {"role": "user", "content": START_MSG}]
        self.body = {"model": s.model, "temperature": s.temperature, "max_tokens": s.max_tokens, "stream": True}
        if tools:
            self.body["tools"] = tools
        if s.effort:
            self.body["chat_template_kwargs"] = {"reasoning_effort": s.effort}
        self.tx(f"# Autopilot run {self.id}\n\nTask: {s.task_name}\nRepo: {s.repo}\nVerify: {s.verify or '(none)'}\n"
                f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\nTools: {len(tools)} "
                f"({', '.join(t['function']['name'] for t in tools)})\n\nTASK:\n{s.task.strip()}")
        self.event(kind="start", tools=len(tools), head=(self.start_head or "")[:12])
        self.out(f"autopilot {self.id}: started; {len(tools)} tools; repo {s.repo}; transcript {self.dir}/transcript.md")

    def loop(self):
        s = self.s
        tools_this_turn = 0
        while True:
            self.summary("running")
            if len(self.messages) > s.max_messages:
                self.fresh_chat(f"{len(self.messages)} messages")
                tools_this_turn = 0
            body = dict(self.body, messages=self.messages)
            try:
                (content, calls, finish, rchars), secs = self.call_model(body)
            except FreshChat as e:
                self.fresh_chat(str(e))
                tools_this_turn = 0
                continue
            self.last_reply = content or self.last_reply
            self.event(kind="model", n=self.c["model_calls"], secs=round(secs, 1), finish=finish,
                       content_chars=len(content or ""), reasoning_chars=rchars, tool_calls=len(calls))
            self.tx(f"## {time.strftime('%H:%M:%S')} reply {self.c['model_calls']} ({round(secs)} s, "
                    f"finish {finish}, thinking {rchars} chars)\n{clip(content or '(no text)', 4000)}")
            msg = {"role": "assistant", "content": content or ""}
            if calls:
                for i, tc in enumerate(calls):
                    tc["id"] = tc["id"] or f"call_{self.c['model_calls']}_{i}"
                msg["tool_calls"] = [{"id": tc["id"], "type": "function",
                                      "function": {"name": tc["name"], "arguments": tc["arguments"] or "{}"}}
                                     for tc in calls]
            self.messages.append(msg)

            if calls:
                tools_this_turn += len(calls)
                self.talk_turns = 0
                for tc in calls:
                    self.check_limits()
                    head_before = self.head
                    t = time.time()
                    name, ok, text, blocked = self.run_tool(tc, self.c["tool_calls"])
                    self.c["tool_calls"] += 1
                    self.calls_since_commit += 1
                    self.messages.append({"role": "tool", "tool_call_id": tc["id"], "content": text})
                    self.event(kind="tool", name=name, ok=ok, blocked=blocked, secs=round(time.time() - t, 1),
                               chars=len(text))
                    self.tx(f"-> {name} {short(tc['arguments'], 500)}\n<- {'ok' if ok else 'NOT OK'} "
                            f"({len(text)} chars): {clip(text, 1500)}")
                    self.note_head()
                    sig = hashlib.sha256((name + "\0" + (tc["arguments"] or "") + "\0" + str(head_before)).encode())
                    pair = (sig.hexdigest(), hashlib.sha256(text.encode()).hexdigest())
                    self.recent.append(pair)
                    if self.recent.count(pair) >= s.repeat_limit:
                        raise Stop("stuck", f"the same call gave the same result {s.repeat_limit} times with no "
                                            f"commit in between: {name} {short(tc['arguments'], 200)}")
                continue

            # the reply ended without tool calls: Jarvis stopped
            word, rest = parse_status(content)
            if word:
                self.last_status = f"STATUS: {word}" + (f": {rest}" if rest else "")
            if word == "DONE":
                problems = self.check_done()
                if not problems:
                    raise Stop("done", "STATUS: DONE and every check passed")
                self.c["done_rejected"] += 1
                self.event(kind="done_rejected", n=self.c["done_rejected"])
                note = ("[AUTOPILOT: you wrote STATUS: DONE, but the check failed:\n" + "\n".join(problems) +
                        "\nFix it and finish again, or end with STATUS: BLOCKED: <reason>.]")
                self.tx("DONE REJECTED:\n" + "\n".join(problems))
                self.messages.append({"role": "user", "content": note})
            elif word == "BLOCKED":
                raise Stop("blocked", rest or "no reason given")
            elif finish == "length":
                self.c["length_nudges"] += 1
                self.messages.append({"role": "user", "content": LENGTH_MSG})
                self.tx("LENGTH NUDGE sent")
            else:
                if tools_this_turn == 0:
                    self.talk_turns += 1
                self.c["continues"] += 1
                self.event(kind="continue", n=self.c["continues"])
                self.tx(f"CONTINUE sent ({self.c['continues']})")
                self.messages.append({"role": "user", "content": CONTINUE_MSG})
            tools_this_turn = 0

    def execute(self):
        """Run to the end. Returns (exit code, summary dict)."""
        status, reason = "error", "unknown"
        try:
            self.start()
            self.loop()
        except Stop as e:
            status, reason = e.status, e.reason
        except KeyboardInterrupt:
            status, reason = "stopped", "stopped by a signal (systemctl stop or Ctrl-C)"
        except Exception as e:  # never die silently: record it
            status, reason = "error", f"{type(e).__name__}: {short(e, 400)}"
        d = self.summary(status, reason)
        self.event(kind="stop", status=status)
        self.tx(f"## STOP: {status}: {reason}\nCounts: {json.dumps(self.c)}\nCommits: {len(d['commits'])}")
        title = {"done": "Jarvis autopilot: DONE", "blocked": "Jarvis autopilot: BLOCKED"}.get(
            status, f"Jarvis autopilot stopped: {status}")
        body = (f"{self.s.task_name}: {reason}\n{len(d['commits'])} commits, {self.c['tool_calls']} tool calls, "
                f"{self.c['continues']} continues, {d['minutes']} min.\nRun {self.id}")
        sent = notify(self.s, title, body, priority=3 if status == "done" else 4)
        self.out(f"autopilot {self.id}: {status}: {reason} (notification {sent})")
        code = {"done": EXIT_DONE, "blocked": EXIT_BLOCKED, "error": EXIT_ERROR}.get(status, EXIT_STOPPED)
        return code, d


# ---------------------------------------------------------------- --check and --status

def run_check(s, out=print):
    results = []

    def res(ok, name, detail=""):
        results.append(ok)
        out(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}".rstrip())

    out(f"proxy {s.proxy_url} (key {'set' if s.proxy_key else 'NOT set'}); tools {s.tools_url} "
        f"(key: {s.tools_key_source}); repo {s.repo}; ntfy {'set' if s.ntfy_url else 'not set'}")
    root = re.sub(r"/v1/?$", "", s.proxy_url.rstrip("/"))
    try:
        h = httpx.get(root + "/ctxproxy/health", timeout=10).json()
        res(bool(h.get("ok")), "proxy health", f"compact_at {h.get('compact_at')}, new-chat note "
                                                 f"{'on' if h.get('resume_new_chats') else 'OFF'}")
    except Exception as e:
        res(False, "proxy health", type(e).__name__)
    m = Model(s)
    model = s.model
    try:
        ids = m.models()
        model = model or (ids[0] if ids else "")
        res(bool(ids), "model list through the proxy", f"{model}")
    except Exception as e:
        res(False, "model list through the proxy", short(e, 200))
    try:
        reply = m.ping(model)
        res(bool(reply), "model answers through the proxy", repr(short(reply, 40)))
    except Exception as e:
        res(False, "model answers through the proxy", short(e, 200))
    try:  # the exact streamed tool-call path a run uses; nothing is executed
        probe_tool = {"type": "function", "function": {"name": "echo_probe", "description": "Echo a word back.",
                      "parameters": {"type": "object", "properties": {"text": {"type": "string"}},
                                     "required": ["text"]}}}
        body = {"model": model, "stream": True, "temperature": 0, "max_tokens": 300, "tools": [probe_tool],
                "chat_template_kwargs": {"enable_thinking": False},
                "messages": [{"role": "user", "content": "Call the echo_probe tool with text 'ping'. Do not "
                                                         "answer in text."}]}
        content, calls, finish, _ = m.chat(body, {"X-Ctxproxy-No-Resume": "1"})
        args = json.loads(calls[0]["arguments"] or "{}") if calls else {}
        res(bool(calls) and calls[0]["name"] == "echo_probe" and args.get("text") == "ping",
            "model makes a streamed tool call", f"finish {finish}; " + (
                f"{calls[0]['name']}({calls[0]['arguments']})" if calls else f"no tool call, text {short(content, 80)!r}"))
    except Exception as e:
        res(False, "model makes a streamed tool call", short(e, 200))
    ts = ToolServer(s.tools_url, s.tools_key, 60)
    try:
        tools = ts.load()
        names = [t["function"]["name"] for t in tools]
        belt = Seatbelt(s)
        off = [n for n in names if belt.check(n, {}) is not None]
        res(bool(names), "tool server lists tools", f"{len(names)}: {', '.join(names)}"
            + (f"; off in this run: {', '.join(off)}" if off else ""))
        probe = next((n for n in names if n in ("list_tools", "sys_summary", "gpu_status")), None)
        if probe:
            ok, text = ts.call(probe, {})
            res(ok, f"tool key works (called read-only {probe})", "" if ok else short(text, 200))
        else:
            out("INFO  no read-only probe tool found; the key is tested on the first real call")
    except Exception as e:
        res(False, "tool server lists tools", short(e, 200))
    try:
        p = extract_prompt(s.prompt_file)
        res("STATUS: DONE" in p, "Builder prompt v2 found", f"{len(p)} chars from {s.prompt_file}"
            + ("" if "STATUS: DONE" in p else "; it has no STATUS: DONE rule (old prompt?)"))
    except Exception as e:
        res(False, "Builder prompt found", short(e, 200))
    head = git_head(s.repo)
    res(head is not None, "repo is a git repo", f"{s.repo} HEAD {(head or '')[:10]}")
    if os.path.exists(s.pause_file):
        out(f"WARN  PAUSE file present: {s.pause_file} (a run would stop at once; delete it to run)")
    out(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


def latest_run(runs_dir):
    try:
        dirs = sorted(d for d in os.listdir(runs_dir) if os.path.isdir(os.path.join(runs_dir, d)))
    except FileNotFoundError:
        return None
    return os.path.join(runs_dir, dirs[-1]) if dirs else None


def show_status(s, out=print, lines=25):
    d = latest_run(s.runs_dir)
    if not d:
        out("no runs yet")
        return 1
    try:
        sm = json.load(open(os.path.join(d, "summary.json"), encoding="utf-8"))
    except (OSError, ValueError):
        out(f"{d}: no readable summary.json")
        return 1
    alive = False
    try:
        os.kill(int(sm.get("pid", 0)), 0)
        alive = sm.get("status") in ("running", "starting")
    except (OSError, ValueError):
        pass
    state = sm.get("status") + (" (process alive)" if alive else ("" if sm.get("status") not in
                                                                     ("running", "starting") else " (process gone)"))
    out(f"run {sm.get('id')}: {state}. {sm.get('reason', '')}")
    out(f"task: {sm.get('task')} | started {sm.get('started')} | {sm.get('minutes')} min | model calls "
        f"{sm.get('model_calls')}, tool calls {sm.get('tool_calls')}, continues {sm.get('continues')}, "
        f"seatbelt {sm.get('seatbelt')}")
    out(f"commits ({len(sm.get('commits', []))}): " + "; ".join(sm.get("commits", [])[:8]))
    if sm.get("last_status_line"):
        out("last status line: " + sm["last_status_line"])
    try:
        tail = open(os.path.join(d, "transcript.md"), encoding="utf-8").read().splitlines()[-lines:]
        out(f"--- last {len(tail)} transcript lines ({d}/transcript.md) ---")
        for ln in tail:
            out(ln[:300])
    except OSError:
        pass
    return 0


# ---------------------------------------------------------------- main

def parse_args(argv):
    p = argparse.ArgumentParser(description="Run one approved Builder task without anyone typing 'continue'.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="preflight checks, changes nothing")
    g.add_argument("--status", action="store_true", help="show the latest run")
    g.add_argument("--task", help="the task text")
    g.add_argument("--task-file", help="file with the task text")
    p.add_argument("--repo", help="git repo whose commits count as progress (default ~/jarvis-build)")
    p.add_argument("--verify", help="shell command that must exit 0 before DONE is accepted")
    p.add_argument("--no-require-commit", action="store_true")
    p.add_argument("--no-require-clean", action="store_true")
    p.add_argument("--allow-create-tool", action="store_true", help="for steps whose spec says create_tool")
    p.add_argument("--deny-tools", default="", help="comma-separated tool names to turn off")
    p.add_argument("--write-root", action="append", default=[], help="extra folder write tools may write in")
    p.add_argument("--max-hours", type=float)
    p.add_argument("--max-tool-calls", type=int)
    p.add_argument("--max-continues", type=int)
    p.add_argument("--max-calls-without-commit", type=int)
    p.add_argument("--max-tokens", type=int)
    p.add_argument("--effort", choices=["low", "medium", "xhigh"], help="reasoning effort (default: the server's)")
    p.add_argument("--model")
    p.add_argument("--prompt-file")
    p.add_argument("--proxy-url")
    p.add_argument("--tools-url")
    return p.parse_args(argv)


def build_settings(a):
    s = settings_from_env()
    if a.task_file:
        s.task = open(os.path.expanduser(a.task_file), encoding="utf-8").read()
        s.task_name = os.path.basename(a.task_file)
    elif a.task:
        s.task, s.task_name = a.task, short(a.task, 60)
    for attr, val in [("repo", a.repo), ("verify", a.verify), ("max_hours", a.max_hours),
                      ("max_tool_calls", a.max_tool_calls), ("max_continues", a.max_continues),
                      ("max_calls_without_commit", a.max_calls_without_commit), ("max_tokens", a.max_tokens),
                      ("effort", a.effort), ("model", a.model), ("prompt_file", a.prompt_file),
                      ("proxy_url", a.proxy_url), ("tools_url", a.tools_url)]:
        if val is not None:
            setattr(s, attr, os.path.expanduser(val) if attr in ("repo", "prompt_file") else val)
    s.require_commit = not a.no_require_commit
    s.require_clean = not a.no_require_clean
    s.allow_create_tool = a.allow_create_tool
    s.deny_tools = tuple(t.strip() for t in a.deny_tools.split(",") if t.strip())
    s.write_roots = tuple(s.write_roots) + tuple(os.path.expanduser(r) for r in a.write_root)
    return s


def main(argv=None):
    a = parse_args(sys.argv[1:] if argv is None else argv)
    s = build_settings(a)
    if a.check:
        return run_check(s)
    if a.status:
        return show_status(s)
    if not s.task.strip():
        print("the task is empty", file=sys.stderr)
        return EXIT_ERROR
    os.makedirs(s.runs_dir, exist_ok=True)
    lock = open(os.path.join(s.runs_dir, ".lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another autopilot run is active (runs/.lock is held)", file=sys.stderr)
        return EXIT_ERROR

    def on_term(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, on_term)
    code, _ = Run(s).execute()
    return code


if __name__ == "__main__":
    sys.exit(main())
