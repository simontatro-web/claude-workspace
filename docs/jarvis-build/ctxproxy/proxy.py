#!/usr/bin/env python3
"""Context proxy for Jarvis Builder (J3 v2).

Sits between Open WebUI and llama-server. Every chat request (each round of a
tool loop included) is counted; near the limit it adds a CONTEXT HIGH note,
over the limit it compacts to a frozen, sticky view so the prompt cache keeps
working. The first request of a new chat gets a NEW CHAT START note (the
RESUME HERE block plus git facts), frozen for the rest of that chat.
Everything else is forwarded unchanged. Fails open, but never forwards a
request that cannot fit.

Run: python proxy.py  (settings from environment, see Config)
"""
import asyncio
import contextlib
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

try:
    from zoneinfo import ZoneInfo
    CHICAGO = ZoneInfo("America/Chicago")
except Exception:  # tzdata missing: fall back to UTC
    CHICAGO = None

HOME = os.path.expanduser("~")


def _env(name, default, cast=str):
    v = os.environ.get("CTXPROXY_" + name)
    return default if v is None or v == "" else cast(v)


def _bool(v):
    return str(v).strip().lower() not in ("0", "false", "no", "off", "")


@dataclass
class Config:
    host: str = field(default_factory=lambda: _env("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env("PORT", 8113, int))
    upstream: str = field(default_factory=lambda: _env("UPSTREAM", "http://127.0.0.1:8080"))
    # Optional client key: if set, requests must carry "Authorization: Bearer <key>".
    client_key: str = field(default_factory=lambda: _env("CLIENT_KEY", ""))
    # Optional key sent to llama-server (replaces the client's Authorization header).
    upstream_key: str = field(default_factory=lambda: _env("UPSTREAM_KEY", ""))

    limit: int = field(default_factory=lambda: _env("LIMIT", 24576, int))
    reserve: int = field(default_factory=lambda: _env("RESERVE", 6000, int))
    warn_gap: int = field(default_factory=lambda: _env("WARN_GAP", 3000, int))
    keep_margin: int = field(default_factory=lambda: _env("KEEP_MARGIN", 6000, int))
    min_output: int = field(default_factory=lambda: _env("MIN_OUTPUT", 1024, int))
    overhead_pct: float = field(default_factory=lambda: _env("OVERHEAD_PCT", 3.0, float))
    per_msg_tokens: int = field(default_factory=lambda: _env("PER_MSG_TOKENS", 5, int))
    tools_extra_tokens: int = field(default_factory=lambda: _env("TOOLS_EXTRA_TOKENS", 200, int))

    msg_cut_over: int = field(default_factory=lambda: _env("MSG_CUT_OVER", 4000, int))
    msg_cut_head: int = field(default_factory=lambda: _env("MSG_CUT_HEAD", 2500, int))
    msg_cut_tail: int = field(default_factory=lambda: _env("MSG_CUT_TAIL", 1000, int))

    progress_path: str = field(default_factory=lambda: _env("PROGRESS", HOME + "/jarvis-build/PROGRESS.md"))
    handoff_max_chars: int = field(default_factory=lambda: _env("HANDOFF_MAX_CHARS", 6000, int))
    handoff_stale_s: int = field(default_factory=lambda: _env("HANDOFF_STALE_S", 1800, int))
    summary_timeout_s: float = field(default_factory=lambda: _env("SUMMARY_TIMEOUT_S", 60.0, float))
    summary_max_tokens: int = field(default_factory=lambda: _env("SUMMARY_MAX_TOKENS", 800, int))
    summary_input_tokens: int = field(default_factory=lambda: _env("SUMMARY_INPUT_TOKENS", 12000, int))

    # A new chat's first request gets a NEW CHAT START note (RESUME HERE + git facts), kept identical
    # for the rest of that chat. Per request: header "X-Ctxproxy-No-Resume: 1" turns it off.
    resume_new_chats: bool = field(default_factory=lambda: _env("RESUME_NEW_CHATS", True, _bool))
    # Repo whose `git log --oneline -5` and `git status --short` go into both notes ("" = none).
    git_dir: str = field(default_factory=lambda: _env("GIT_DIR", HOME + "/jarvis-build"))
    git_timeout_s: float = field(default_factory=lambda: _env("GIT_TIMEOUT_S", 3.0, float))

    tokenize_timeout_s: float = field(default_factory=lambda: _env("TOKENIZE_TIMEOUT_S", 3.0, float))
    connect_timeout_s: float = field(default_factory=lambda: _env("CONNECT_TIMEOUT_S", 5.0, float))
    read_timeout_s: float = field(default_factory=lambda: _env("READ_TIMEOUT_S", 300.0, float))
    total_timeout_s: float = field(default_factory=lambda: _env("TOTAL_TIMEOUT_S", 1800.0, float))
    max_body_bytes: int = field(default_factory=lambda: _env("MAX_BODY_BYTES", 64 * 1024 * 1024, int))

    state_dir: str = field(default_factory=lambda: _env("STATE_DIR", HOME + "/jarvis-build/ctxproxy"))
    max_states: int = field(default_factory=lambda: _env("MAX_STATES", 50, int))
    events_max_bytes: int = field(default_factory=lambda: _env("EVENTS_MAX_BYTES", 5 * 1024 * 1024, int))
    fault: str = field(default_factory=lambda: _env("FAULT", ""))  # test hook only

    @property
    def compact_at(self):
        return self.limit - self.reserve - 1000

    @property
    def warn_at(self):
        return self.compact_at - self.warn_gap

    @property
    def hard_max(self):
        return self.limit - self.min_output


HOP_HEADERS = {"host", "content-length", "transfer-encoding", "connection", "keep-alive",
               "proxy-authenticate", "proxy-authorization", "te", "trailer", "upgrade",
               "accept-encoding", "x-ctxproxy-skip", "x-ctxproxy-no-resume"}
RESP_DROP = {"content-length", "transfer-encoding", "connection", "keep-alive", "content-encoding"}


class TooLarge(Exception):
    pass


# ---------------------------------------------------------------- text helpers

def content_text(content):
    """Text of a message content: str, or a list of parts (text parts joined)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for p in content:
            if isinstance(p, dict) and isinstance(p.get("text"), str):
                out.append(p["text"])
            elif isinstance(p, str):
                out.append(p)
        return "\n".join(out)
    return str(content)


def message_text(m):
    """Everything in a message that the chat template renders as text."""
    parts = [str(m.get("role", "")), content_text(m.get("content"))]
    if isinstance(m.get("reasoning_content"), str):
        parts.append(m["reasoning_content"])
    for tc in m.get("tool_calls") or []:
        try:
            parts.append(json.dumps(tc.get("function", tc), ensure_ascii=False))
        except Exception:
            parts.append(str(tc))
    if m.get("name"):
        parts.append(str(m["name"]))
    return "\n".join(p for p in parts if p)


def canonical(m):
    """Stable identity of a message for the history hash chain."""
    d = {"r": m.get("role"), "c": content_text(m.get("content")),
         "t": m.get("tool_calls") or None, "i": m.get("tool_call_id"), "n": m.get("name")}
    return json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8", "replace")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def append_text(content, extra):
    """Append text to a message content of either shape."""
    if isinstance(content, list):
        return list(content) + [{"type": "text", "text": extra}]
    return (content or "") + extra


def now_chicago(ts=None):
    if CHICAGO is None:
        return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ts or time.time()))
    import datetime
    return datetime.datetime.fromtimestamp(ts or time.time(), CHICAGO).strftime("%Y-%m-%d %H:%M Chicago")


# ---------------------------------------------------------------- the proxy

class Proxy:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = None
        self.tok_cache = OrderedDict()
        self.states = OrderedDict()  # prefix hash -> state dict
        self.resumes = OrderedDict()  # chat-root hash -> NEW CHAT START note
        self.events_lock = threading.Lock()
        self.tokenize_ok = True
        os.makedirs(cfg.state_dir, exist_ok=True)
        self.state_path = os.path.join(cfg.state_dir, "state.json")
        self.resume_path = os.path.join(cfg.state_dir, "resumes.json")
        self.events_path = os.path.join(cfg.state_dir, "events.jsonl")
        self._load_state()
        self._load_resumes()

    # ---- state persistence
    def _load_state(self):
        try:
            with open(self.state_path, encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                if isinstance(v, dict) and "cut" in v and "note" in v:
                    self.states[k] = v
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"ctxproxy: state.json unreadable, starting empty ({type(e).__name__})", file=sys.stderr)

    def _save_state(self):
        while len(self.states) > self.cfg.max_states:
            self.states.popitem(last=False)
        tmp = self.state_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.states, f, ensure_ascii=False)
            os.replace(tmp, self.state_path)
        except Exception as e:
            print(f"ctxproxy: cannot save state ({type(e).__name__})", file=sys.stderr)

    def _load_resumes(self):
        try:
            with open(self.resume_path, encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                if isinstance(v, dict) and "note" in v and "note_tokens" in v:
                    self.resumes[k] = v
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"ctxproxy: resumes.json unreadable, starting empty ({type(e).__name__})", file=sys.stderr)

    def _save_resumes(self):
        while len(self.resumes) > self.cfg.max_states:
            self.resumes.popitem(last=False)
        tmp = self.resume_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.resumes, f, ensure_ascii=False)
            os.replace(tmp, self.resume_path)
        except Exception as e:
            print(f"ctxproxy: cannot save resumes ({type(e).__name__})", file=sys.stderr)

    # ---- events (metadata only, never message text or headers)
    def event(self, **kw):
        kw = {"ts": round(time.time(), 3), **kw}
        line = json.dumps(kw, ensure_ascii=True) + "\n"
        with self.events_lock:
            try:
                try:
                    if os.path.getsize(self.events_path) > self.cfg.events_max_bytes:
                        os.replace(self.events_path, self.events_path + ".1")
                except FileNotFoundError:
                    pass
                with open(self.events_path, "a", encoding="ascii") as f:
                    f.write(line)
            except Exception as e:
                print(f"ctxproxy: cannot write events ({type(e).__name__})", file=sys.stderr)

    # ---- token counting
    def _estimate(self, text):
        return max(1, len(text) // 3) if text else 0

    async def _tokenize_one(self, text, headers):
        r = await self.client.post(self.cfg.upstream + "/tokenize", json={"content": text},
                                   headers=headers, timeout=self.cfg.tokenize_timeout_s)
        r.raise_for_status()
        toks = r.json().get("tokens")
        if not isinstance(toks, list):
            raise ValueError("bad tokenize reply")
        return len(toks)

    async def count_texts(self, texts, headers):
        """Token count of each text. /tokenize with a cache; len//3 for any it cannot count."""
        keys = [sha(t.encode("utf-8", "replace")) for t in texts]
        missing = {}
        for k, t in zip(keys, texts):
            if k in self.tok_cache:
                self.tok_cache.move_to_end(k)
            elif t:
                missing[k] = t
        if missing:
            sem = asyncio.Semaphore(8)

            async def one(k, t):
                async with sem:
                    return k, await self._tokenize_one(t, headers)

            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*(one(k, t) for k, t in missing.items()), return_exceptions=True),
                    timeout=self.cfg.tokenize_timeout_s)
            except asyncio.TimeoutError:
                results = []
            got = {r[0]: r[1] for r in results if isinstance(r, tuple)}
            self.tokenize_ok = len(got) == len(missing)
            for k, n in got.items():
                self.tok_cache[k] = n
            while len(self.tok_cache) > 20000:
                self.tok_cache.popitem(last=False)
            fallback = {k: self._estimate(t) for k, t in missing.items() if k not in got}
        else:
            fallback = {}
        out = []
        for k, t in zip(keys, texts):
            if not t:
                out.append(0)
            elif k in self.tok_cache:
                out.append(self.tok_cache[k])
            else:
                out.append(fallback[k])
        return out

    def total(self, msg_counts, tools_count):
        raw = sum(msg_counts) + self.cfg.per_msg_tokens * len(msg_counts) + tools_count
        return int(raw * (1 + self.cfg.overhead_pct / 100.0))

    # ---- oversized message cuts (deterministic, so the prefix stays stable)
    def cut_message(self, m, ntok):
        c = self.cfg
        if m.get("role") == "system" or ntok <= c.msg_cut_over:
            return m, False
        text = content_text(m.get("content"))
        if not text:
            return m, False
        chars_per_tok = max(1.0, len(text) / max(1, ntok))
        head = int(c.msg_cut_head * chars_per_tok)
        tail = int(c.msg_cut_tail * chars_per_tok)
        if head + tail >= len(text):
            return m, False
        removed = ntok - c.msg_cut_head - c.msg_cut_tail
        new_text = (text[:head] + f"\n\n[CUT BY CONTEXT PROXY: about {removed} tokens removed from the middle]\n\n"
                    + text[-tail:])
        m2 = dict(m)
        m2["content"] = new_text
        return m2, True

    # ---- handoff
    def read_handoff(self):
        """(text or None, mtime or None). The RESUME HERE block of PROGRESS.md."""
        try:
            st = os.stat(self.cfg.progress_path)
            with open(self.cfg.progress_path, "rb") as f:
                raw = f.read(2 * 1024 * 1024)
        except Exception:
            return None, None
        text = raw.decode("utf-8", "replace")
        lines = text.splitlines()
        start = None
        for i, ln in enumerate(lines):
            if ln.strip().lower().startswith("## resume here"):
                start = i
                break
        if start is None:
            return None, st.st_mtime
        block = [lines[start]]
        for ln in lines[start + 1:]:
            if ln.startswith("## ") or ln.startswith("# "):
                break
            block.append(ln)
        out = "\n".join(block).strip()
        if len(out.splitlines()) <= 1:
            return None, st.st_mtime
        if len(out) > self.cfg.handoff_max_chars:
            out = out[:self.cfg.handoff_max_chars] + "\n[handoff cut at %d chars]" % self.cfg.handoff_max_chars
        return out, st.st_mtime

    def git_facts(self):
        """Last 5 commits and uncommitted files of cfg.git_dir, read-only. None if disabled."""
        d = self.cfg.git_dir
        if not d:
            return None
        shown = d.replace(HOME, "~", 1) if d.startswith(HOME) else d
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"})

        def git(*args):
            r = subprocess.run(["git", "--no-optional-locks", "-C", d, *args], capture_output=True, text=True,
                               timeout=self.cfg.git_timeout_s, env=env, errors="replace")
            if r.returncode != 0:
                first = (r.stderr or "").strip().splitlines()
                raise RuntimeError(first[0][:160] if first else f"git exit {r.returncode}")
            return [ln[:200] for ln in r.stdout.splitlines()]

        try:
            log = git("log", "--oneline", "-5") or ["(no commits yet)"]
            status = git("status", "--short")
        except FileNotFoundError:
            return f"Git facts for {shown}: unavailable (git not found)."
        except subprocess.TimeoutExpired:
            return f"Git facts for {shown}: unavailable (git timed out)."
        except Exception as e:
            return f"Git facts for {shown}: unavailable ({e})."
        if len(status) > 15:
            status = status[:15] + [f"... and {len(status) - 15} more"]
        return (f"Last commits in {shown} (git log --oneline -5):\n" + "\n".join(log) +
                f"\nUncommitted changes in {shown} (git status --short):\n" +
                ("\n".join(status) if status else "(none, working tree clean)"))

    async def build_resume_note(self, headers):
        handoff, mtime = self.read_handoff()
        facts = await asyncio.to_thread(self.git_facts)
        shown = self.cfg.progress_path.replace(HOME, "~", 1)
        parts = [f"NEW CHAT START note from the context proxy ({now_chicago()}). Your saved state:"]
        if handoff:
            parts.append(f"RESUME HERE block of {shown} (last changed {now_chicago(mtime)}):\n{handoff}")
        else:
            parts.append(f"No RESUME HERE block found in {shown}.")
        if facts:
            parts.append(facts)
        parts.append("Continue from the exact next action above unless Simon's message says otherwise. "
                     "Re-check any fact with a tool before relying on it. Never redo committed work.")
        note = "\n".join(parts)
        note_tokens = (await self.count_texts([note], headers))[0]
        return {"note": note, "note_tokens": note_tokens, "created": round(time.time())}

    async def auto_summary(self, removed, removed_counts, headers):
        c = self.cfg
        picked, used = [], 0
        for m, n in zip(reversed(removed), reversed(removed_counts)):
            if used + n > c.summary_input_tokens:
                if not picked:  # one giant message: take its tail
                    t = message_text(m)
                    picked.append(t[-c.summary_input_tokens * 3:])
                break
            picked.append(message_text(m))
            used += n
        transcript = "\n\n".join(reversed(picked))
        body = {
            "messages": [
                {"role": "system", "content": "You summarise a work session so it can continue. Be concrete and short."},
                {"role": "user", "content": "Summarise this session transcript as four short sections: GOAL, DONE (with commit hashes if shown), NEXT ACTION (the exact next step), OPEN PROBLEMS. Only state what the transcript shows.\n\n" + transcript},
            ],
            "max_tokens": c.summary_max_tokens,
            "temperature": 0,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        h = dict(headers)
        h["x-ctxproxy-skip"] = "1"
        try:
            r = await self.client.post(c.upstream + "/v1/chat/completions", json=body, headers=h,
                                       timeout=c.summary_timeout_s)
            r.raise_for_status()
            txt = r.json()["choices"][0]["message"].get("content") or ""
            txt = txt.strip()
            if len(txt) < 20:
                return None, "summary_empty"
            return txt[:c.handoff_max_chars], None
        except Exception as e:
            return None, "summary_" + type(e).__name__

    # ---- the core transform
    async def transform(self, body, headers, no_resume=False):
        """Returns (new_body or None if unchanged, info dict)."""
        c = self.cfg
        info = {}
        msgs = body.get("messages")
        if not isinstance(msgs, list) or not msgs:
            info["action"] = "pass"
            return None, info
        if c.fault == "transform":
            raise RuntimeError("fault injection")

        lead_sys = []
        for i, m in enumerate(msgs):  # leading system messages only
            if m.get("role") == "system":
                lead_sys.append(m)
            else:
                break
        rest = msgs[len(lead_sys):]
        tools = body.get("tools")
        tools_text = json.dumps(tools, ensure_ascii=False, sort_keys=True) if tools else ""

        texts = [message_text(m) for m in lead_sys] + [message_text(m) for m in rest] + [tools_text]
        counts = await self.count_texts(texts, headers)
        sys_counts = counts[:len(lead_sys)]
        rest_counts = counts[len(lead_sys):len(lead_sys) + len(rest)]
        tools_count = counts[-1] + (c.tools_extra_tokens if tools else 0)
        info["tokenize_ok"] = self.tokenize_ok

        before = self.total(sys_counts + rest_counts, tools_count)
        info["tok_before"] = before

        # oversized single messages
        cut_rest, cut_n = [], 0
        for m, n in zip(rest, rest_counts):
            m2, did = self.cut_message(m, n)
            cut_rest.append(m2)
            cut_n += did
        if cut_n:
            new_counts = await self.count_texts([message_text(m) for m in cut_rest], headers)
            rest_counts = new_counts
        info["cut"] = cut_n

        # history hash chain over non-system messages (original content)
        chain = [sha(b"")]
        for m in rest:
            chain.append(sha((chain[-1]).encode() + canonical(m)))

        # sticky state: latest compaction whose prefix matches this history
        state = None
        for k in range(len(rest), 0, -1):
            st = self.states.get(chain[k])
            if st is not None and st.get("cut") == k:
                state = st
                break

        # new-chat note: frozen per chat, so every later request of the chat gets the same prefix
        resume = None
        if state is None and c.resume_new_chats and not no_resume and rest and rest[0].get("role") == "user":
            if len(rest) == 1:
                resume = await self.build_resume_note(headers)
                self.resumes[chain[1]] = resume
                self.resumes.move_to_end(chain[1])
                self._save_resumes()
                info["resume"] = "new"
            else:
                # chain[2] (opener + first reply) wins over chain[1], so a later chat that starts
                # with the same opener cannot swap this chat's note
                resume = self.resumes.get(chain[2]) or self.resumes.get(chain[1])
                if resume is not None:
                    if chain[2] not in self.resumes:
                        self.resumes[chain[2]] = resume
                        self._save_resumes()
                    info["resume"] = "sticky"
            if resume is not None:
                info["resume_tokens"] = resume["note_tokens"]

        def render(st):
            if st is None and resume is None:
                return list(lead_sys), list(cut_rest), list(sys_counts), list(rest_counts)
            src = st if st is not None else resume
            note = src["note"]
            if lead_sys:
                first = dict(lead_sys[0])
                first["content"] = append_text(first.get("content"), "\n\n" + note)
                s_msgs = [first] + list(lead_sys[1:])
                s_counts = [sys_counts[0] + src["note_tokens"]] + list(sys_counts[1:])
            else:
                s_msgs = [{"role": "system", "content": note}]
                s_counts = [src["note_tokens"]]
            if st is None:
                return s_msgs, list(cut_rest), s_counts, list(rest_counts)
            k = st["cut"]
            r_msgs, r_counts = [], []
            pin = st.get("pin")
            if pin is not None and pin < k:
                r_msgs.append(cut_rest[pin])
                r_counts.append(rest_counts[pin])
            r_msgs += cut_rest[k:]
            r_counts += rest_counts[k:]
            return s_msgs, r_msgs, s_counts, r_counts

        s_msgs, r_msgs, s_counts, r_counts = render(state)
        now_tok = self.total(s_counts + r_counts, tools_count)
        action = "sticky" if state else ("resume" if resume else ("cut" if cut_n else "pass"))

        if now_tok >= c.compact_at:
            if c.fault == "compact":
                raise RuntimeError("fault injection")
            new_state, why = await self.compact(lead_sys, rest, cut_rest, rest_counts, sys_counts,
                                                tools_count, chain, headers)
            if new_state is not None:
                self.states[chain[new_state["cut"]]] = new_state
                self.states.move_to_end(chain[new_state["cut"]])
                self._save_state()
                state = new_state
                s_msgs, r_msgs, s_counts, r_counts = render(state)
                now_tok = self.total(s_counts + r_counts, tools_count)
                action = "compact"
                info["handoff"] = why
                if "resume" in info:
                    info["resume"] = "replaced"

        warned = False
        if now_tok >= c.warn_at:
            note = (f"\n\n[CONTEXT HIGH ({now_tok}/{c.limit}) from the context proxy: finish the current small "
                    "step, update the RESUME HERE block in ~/jarvis-build/PROGRESS.md with the exact next "
                    "action, commit, then continue working. The proxy will compact soon; the RESUME HERE "
                    "block is kept.]")
            if r_msgs and r_msgs[-1].get("role") in ("user", "tool"):
                last = dict(r_msgs[-1])
                last["content"] = append_text(last.get("content"), note)
                r_msgs = r_msgs[:-1] + [last]
            else:
                r_msgs = r_msgs + [{"role": "user", "content": note.strip()}]
            warned = True
            if action == "pass":
                action = "warn"

        info["action"] = action
        info["warned"] = warned
        info["tok_after"] = now_tok
        info["msgs_in"] = len(msgs)
        info["msgs_out"] = len(s_msgs) + len(r_msgs)
        if now_tok > c.hard_max:
            raise TooLarge(now_tok)

        if action == "pass" and not warned:
            return None, info
        new_body = dict(body)
        new_body["messages"] = s_msgs + r_msgs
        return new_body, info

    async def compact(self, lead_sys, rest, cut_rest, rest_counts, sys_counts, tools_count, chain, headers):
        c = self.cfg
        # units: an assistant message with tool_calls plus its following tool results stay together
        units, i = [], 0
        while i < len(rest):
            j = i + 1
            if rest[i].get("role") == "assistant" and rest[i].get("tool_calls"):
                while j < len(rest) and rest[j].get("role") == "tool":
                    j += 1
            units.append((i, j))
            i = j
        last_user = max((i for i, m in enumerate(rest) if m.get("role") == "user"), default=None)

        # handoff text (the note must be built before we know its size)
        handoff, mtime = self.read_handoff()
        why = "resume_here"
        stale = mtime is None or (time.time() - mtime) > c.handoff_stale_s
        # the summary only covers what will be removed; estimate the cut with a provisional note size
        provisional_note_tokens = 2500
        cut_k, pin = self._choose_cut(units, rest_counts, last_user, sys_counts, tools_count,
                                      provisional_note_tokens)
        if cut_k is None:
            return None, "nothing_to_cut"
        if handoff is None or stale:
            removed = [rest[i] for i in range(cut_k) if i != pin]
            removed_counts = [rest_counts[i] for i in range(cut_k) if i != pin]
            summ, err = await self.auto_summary(removed, removed_counts, headers) if removed else (None, "nothing_removed")
            parts = []
            if handoff is not None:
                parts.append(f"RESUME HERE block (last changed {now_chicago(mtime)}, may be older than the work below):\n{handoff}")
            if summ:
                parts.append("Auto-summary of the removed messages (may be incomplete):\n" + summ)
                why = "auto_summary" if handoff is None else "stale_plus_summary"
            else:
                why = (err or "summary_failed") if handoff is None else "stale_only"
            if not parts:
                parts.append("No handoff available. Re-read ~/jarvis-build/PROGRESS.md and run `git log --oneline -5` before doing anything.")
            handoff_text = "\n\n".join(parts)
        else:
            handoff_text = f"RESUME HERE block (last changed {now_chicago(mtime)}):\n{handoff}"

        facts = await asyncio.to_thread(self.git_facts)
        note = (f"CONTEXT COMPACTED by the context proxy at {now_chicago()}. Earlier messages of this chat were "
                "removed from your view.\n" + handoff_text + ("\n" + facts if facts else "") +
                "\nContinue from the exact next action above. Re-check any fact with a tool before relying on it. "
                "Do not redo committed work: check `git log --oneline -5` first.")
        note_tokens = (await self.count_texts([note], headers))[0]
        cut_k, pin = self._choose_cut(units, rest_counts, last_user, sys_counts, tools_count, note_tokens)
        if cut_k is None:
            return None, "nothing_to_cut"
        return {"cut": cut_k, "pin": pin, "note": note, "note_tokens": note_tokens,
                "created": round(time.time()), "handoff": why}, why

    def _choose_cut(self, units, rest_counts, last_user, sys_counts, tools_count, note_tokens):
        """Index of the first kept message and the pinned user message (or None)."""
        c = self.cfg
        fixed = self.total(list(sys_counts) + [note_tokens], tools_count)
        keep_budget = max(1000, c.compact_at - c.keep_margin - fixed)
        used, cut_k = 0, None
        for (a, b) in reversed(units):
            cost = sum(rest_counts[a:b]) + c.per_msg_tokens * (b - a)
            extra_pin = 0
            if last_user is not None and last_user < a:
                extra_pin = rest_counts[last_user] + c.per_msg_tokens
            if cut_k is not None and used + cost + extra_pin > keep_budget:
                break
            used += cost
            cut_k = a
        if cut_k is None or cut_k == 0:
            return None, None
        pin = last_user if (last_user is not None and last_user < cut_k) else None
        return cut_k, pin


# ---------------------------------------------------------------- HTTP layer

def fwd_headers(req_headers, cfg):
    h = {k: v for k, v in req_headers.items() if k.lower() not in HOP_HEADERS}
    if cfg.client_key:
        h.pop("authorization", None)
        h.pop("Authorization", None)
    if cfg.upstream_key:
        h = {k: v for k, v in h.items() if k.lower() != "authorization"}
        h["authorization"] = "Bearer " + cfg.upstream_key
    return h


def err_json(status, msg):
    return JSONResponse({"error": {"message": "context proxy: " + msg, "type": "ctxproxy_error"}}, status_code=status)


def parse_usage(tail_bytes):
    """Pull llama-server timings/usage from the end of a response (stream or not)."""
    out = {}
    text = tail_bytes.decode("utf-8", "replace")
    cands = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            line = line[5:].strip()
        if line.startswith("{") and ("timings" in line or "usage" in line):
            cands.append(line)
    if not cands and text.strip().startswith("{"):
        cands.append(text.strip())
    for line in reversed(cands):
        try:
            d = json.loads(line)
        except Exception:
            continue
        t = d.get("timings") or {}
        u = d.get("usage") or {}
        if t:
            out["up_prompt_n"] = t.get("prompt_n")
            out["up_cache_n"] = t.get("cache_n")
            out["up_predicted_n"] = t.get("predicted_n")
            out["up_prompt_ms"] = t.get("prompt_ms")
        if u:
            out.setdefault("up_prompt_n", u.get("prompt_tokens"))
            out["up_completion_tokens"] = u.get("completion_tokens")
            det = u.get("completion_tokens_details") or {}
            if det.get("reasoning_tokens") is not None:
                out["up_reasoning_tokens"] = det.get("reasoning_tokens")
        if out:
            break
    return out


def build_app(cfg: Config = None):
    cfg = cfg or Config()
    proxy = Proxy(cfg)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        proxy.client = httpx.AsyncClient(timeout=httpx.Timeout(
            cfg.read_timeout_s, connect=cfg.connect_timeout_s), limits=httpx.Limits(max_connections=64))
        try:
            yield
        finally:
            await proxy.client.aclose()

    async def forward(request: Request, body: bytes, info=None, t0=None):
        url = cfg.upstream + request.url.path
        if request.url.query:
            url += "?" + request.url.query
        headers = fwd_headers(dict(request.headers), cfg)
        t_sent = time.time()
        try:
            up_req = proxy.client.build_request(request.method, url, headers=headers, content=body)
            up = await proxy.client.send(up_req, stream=True)
        except httpx.HTTPError as e:
            if info is not None:
                info["error"] = "upstream_" + type(e).__name__
                proxy.event(**info)
            return err_json(502, f"upstream unreachable ({type(e).__name__})")
        resp_headers = {k: v for k, v in up.headers.items() if k.lower() not in RESP_DROP}
        if info is not None and t0 is not None:
            info["ms_added"] = round((t_sent - t0) * 1000, 1)
            info["status"] = up.status_code

        is_sse = "text/event-stream" in up.headers.get("content-type", "")

        def sse_error(msg):
            return ("data: " + json.dumps({"error": {"message": "context proxy: " + msg}}) + "\n\n").encode()

        async def gen():
            tail = b""
            deadline = t_sent + cfg.total_timeout_s
            completed = False
            try:
                async for chunk in up.aiter_raw():
                    if info is not None:
                        tail = (tail + chunk)[-16384:]
                    yield chunk
                    if time.time() > deadline:
                        if info is not None:
                            info["error"] = "total_timeout"
                        if is_sse:
                            yield sse_error(f"stopped after the {int(cfg.total_timeout_s)} s limit")
                        break
                else:
                    completed = True
            except httpx.HTTPError as e:
                if info is not None:
                    info["error"] = "stream_" + type(e).__name__
                if is_sse:
                    yield sse_error("llama-server stream broke (" + type(e).__name__ + "); the reply is incomplete")
            finally:
                if info is not None:
                    if not completed and "error" not in info:
                        info["error"] = "client_gone"
                    info.update(parse_usage(tail))
                    proxy.event(**info)
                with contextlib.suppress(BaseException):
                    await up.aclose()

        return StreamingResponse(gen(), status_code=up.status_code, headers=resp_headers)

    def auth_ok(request):
        if not cfg.client_key:
            return True
        return request.headers.get("authorization", "") == "Bearer " + cfg.client_key

    async def chat(request: Request):
        t0 = time.time()
        if not auth_ok(request):
            return err_json(401, "bad or missing key")
        body_bytes = await read_body(request)
        if body_bytes is None:
            return err_json(413, "request body too large")
        info = {"path": "chat"}
        skip = request.headers.get("x-ctxproxy-skip") == "1"
        try:
            body = json.loads(body_bytes)
        except Exception:
            info["action"] = "pass_unparsed"
            return await forward(request, body_bytes, info, t0)
        msgs = body.get("messages") if isinstance(body, dict) else None
        if not skip and isinstance(msgs, list) and msgs:
            last_user = next((m for m in reversed(msgs) if isinstance(m, dict) and m.get("role") == "user"), None)
            if last_user and content_text(last_user.get("content")).lstrip().startswith("### Task:"):
                skip = True
        if skip:
            info["action"] = "skip"
            return await forward(request, body_bytes, info, t0)
        try:
            no_resume = request.headers.get("x-ctxproxy-no-resume") == "1"
            new_body, tinfo = await proxy.transform(body, fwd_headers(dict(request.headers), cfg),
                                                    no_resume=no_resume)
            info.update(tinfo)
        except TooLarge as e:
            info.update({"action": "too_large", "tok_after": e.args[0]})
            proxy.event(**info)
            return err_json(400, f"request too large even after compaction ({e.args[0]} tokens, limit {cfg.hard_max}). Start a new chat from RESUME HERE.")
        except Exception as e:
            info.update({"action": "fail_open", "error": type(e).__name__})
            est = len(body_bytes) // 4
            if est > cfg.limit * 2:
                proxy.event(**info)
                return err_json(400, "request too large and the proxy failed to compact it. Start a new chat from RESUME HERE.")
            return await forward(request, body_bytes, info, t0)
        out = body_bytes if new_body is None else json.dumps(new_body, ensure_ascii=False).encode("utf-8")
        return await forward(request, out, info, t0)

    async def read_body(request):
        chunks, size = [], 0
        async for ch in request.stream():
            size += len(ch)
            if size > cfg.max_body_bytes:
                return None
            chunks.append(ch)
        return b"".join(chunks)

    async def passthrough(request: Request):
        if not auth_ok(request):
            return err_json(401, "bad or missing key")
        body = await read_body(request)
        if body is None:
            return err_json(413, "request body too large")
        return await forward(request, body)

    async def health(request: Request):
        return JSONResponse({"ok": True, "compact_at": cfg.compact_at, "warn_at": cfg.warn_at,
                             "states": len(proxy.states), "resume_new_chats": cfg.resume_new_chats,
                             "resumes": len(proxy.resumes)})

    routes = [
        Route("/ctxproxy/health", health, methods=["GET"]),
        Route("/v1/chat/completions", chat, methods=["POST"]),
        Route("/chat/completions", chat, methods=["POST"]),
        Route("/{path:path}", passthrough, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]),
    ]
    app = Starlette(routes=routes, lifespan=lifespan)
    app.state.proxy = proxy
    return app


def make_socket(host, port):
    """Bind with IP_FREEBIND so the unit can start before docker0 has its address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.setsockopt(socket.SOL_IP, 15, 1)  # IP_FREEBIND
    except OSError:
        pass
    s.bind((host, port))
    s.listen(128)
    s.set_inheritable(True)
    return s


def main():
    import uvicorn
    cfg = Config()
    app = build_app(cfg)
    sock = make_socket(cfg.host, cfg.port)
    print(f"ctxproxy on {cfg.host}:{cfg.port} -> {cfg.upstream}; warn {cfg.warn_at}, compact {cfg.compact_at}, "
          f"hard max {cfg.hard_max}", file=sys.stderr)
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", timeout_keep_alive=75))
    asyncio.run(server.serve(sockets=[sock]))


if __name__ == "__main__":
    main()
