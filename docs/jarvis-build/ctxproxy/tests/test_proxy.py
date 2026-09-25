"""Automated stress suite for the context proxy (the A-fake rows of STRESS-PLAN.md).

Run:  venv/bin/python -m pytest -q ctxproxy/tests
Every server binds to 127.0.0.1 on a free port and is stopped at the end.
"""
import json
import os
import random
import socket
import statistics
import sys
import threading
import time

import httpx
import pytest
import uvicorn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import fake_upstream as fu  # noqa: E402
import proxy as px  # noqa: E402


# ---------------------------------------------------------------- servers

def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class ServerThread:
    def __init__(self, app, port):
        self.port = port
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error",
                                                    lifespan="on"))
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


@pytest.fixture(scope="session")
def upstream():
    port = free_port()
    srv = ServerThread(fu.app, port).start()
    yield f"http://127.0.0.1:{port}"
    srv.stop()


@pytest.fixture(autouse=True)
def _reset():
    fu.reset()
    yield


RESUME = """# PROGRESS

## RESUME HERE
- Current step: TEST. Done: edit 01-07 (commit abc1234).
- Exact next action: do edit 08.

## Log
- older stuff that must not be in the handoff
"""


@pytest.fixture
def mkproxy(upstream, tmp_path):
    started = []

    def make(progress=RESUME, **over):
        prog = tmp_path / "PROGRESS.md"
        if progress is not None:
            prog.write_text(progress)
        kw = dict(upstream=upstream, state_dir=str(tmp_path / "state"), progress_path=str(prog),
                  overhead_pct=0.0, per_msg_tokens=0, tools_extra_tokens=0, tokenize_timeout_s=1.0,
                  summary_timeout_s=1.5, resume_new_chats=False, git_dir="")  # the R* tests turn these on
        kw.update(over)
        cfg = px.Config(**kw)
        app = px.build_app(cfg)
        port = free_port()
        srv = ServerThread(app, port).start()
        started.append(srv)
        return f"http://127.0.0.1:{port}", app.state.proxy, cfg, srv

    yield make
    for s in started:
        s.stop()


# ---------------------------------------------------------------- helpers

def W(n, word="w"):
    return " ".join([word] * n)


def msg(role, n_tokens, word="w", **extra):
    """A message whose proxy count is exactly n_tokens (role word counts as 1)."""
    m = {"role": role, "content": W(n_tokens - 1, word)}
    m.update(extra)
    return m


def fwd_count(body):
    n = sum(len(px.message_text(m).split()) for m in body["messages"])
    if body.get("tools"):
        n += len(json.dumps(body["tools"], ensure_ascii=False, sort_keys=True).split())
    return n


def history(total, sys_tokens=100, chunk=1000):
    """system + alternating user/assistant chunks + a final user msg, exact total tokens."""
    msgs = [msg("system", sys_tokens)]
    left = total - sys_tokens
    roles = ["user", "assistant"]
    i = 0
    while left > chunk + 50:
        msgs.append(msg(roles[i % 2], chunk))
        left -= chunk
        i += 1
    if msgs[-1]["role"] == "user":
        msgs.append(msg("assistant", 25))
        left -= 25
    msgs.append(msg("user", left))
    return msgs


def post(base, body, **kw):
    return httpx.post(base + "/v1/chat/completions", json=body, timeout=30, **kw)


def last_fwd():
    chats = [r for r in fu.RECORDED if r["headers"].get("x-ctxproxy-skip") != "1"]
    return chats[-1]["body"]


def all_text(body):
    return "\n".join(px.content_text(m.get("content")) for m in body["messages"])


def events(cfg):
    p = os.path.join(cfg.state_dir, "events.jsonl")
    if not os.path.exists(p):
        return []
    return [json.loads(line) for line in open(p)]


def wait_events(cfg, n, timeout=5):
    t = time.time()
    while time.time() - t < timeout:
        ev = events(cfg)
        if len(ev) >= n:
            return ev
        time.sleep(0.05)
    return events(cfg)


def tool_pair(i, out_tokens, n_calls=1):
    calls = [{"id": f"call_{i}_{k}", "type": "function",
              "function": {"name": "run", "arguments": json.dumps({"cmd": f"step {i}.{k}"})}}
             for k in range(n_calls)]
    a = {"role": "assistant", "content": "", "tool_calls": calls}
    res = [{"role": "tool", "tool_call_id": c["id"], "content": W(out_tokens)} for c in calls]
    return [a] + res


def check_structure(body):
    """No orphan tool results, every tool_call answered, a user message present."""
    msgs = body["messages"]
    assert any(m["role"] == "user" for m in msgs), "no user message"
    open_ids = set()
    for m in msgs:
        if m["role"] == "assistant" and m.get("tool_calls"):
            open_ids = {c["id"] for c in m["tool_calls"]}
        elif m["role"] == "tool":
            assert m["tool_call_id"] in open_ids, "orphan tool result " + m["tool_call_id"]
            open_ids.discard(m["tool_call_id"])
        else:
            assert not open_ids or m["role"] == "system", "tool_call without all results"
            open_ids = set()
    assert not open_ids, "unanswered tool_call at the end"


# ================================================================ COUNTING

def test_C1_exact_thresholds(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    w, c = cfg.warn_at, cfg.compact_at
    for n, expect in [(w - 1, "pass"), (w, "warn"), (c - 1, "warn"), (c, "compact")]:
        body = {"model": "m", "messages": history(n)}
        assert fwd_count(body) == n
        fu.RECORDED.clear()
        r = post(base, body)
        assert r.status_code == 200, r.text
        got = last_fwd()
        text = all_text(got)
        if expect == "pass":
            assert got == body
        elif expect == "warn":
            assert text.count("CONTEXT HIGH") == 1
            assert "CONTEXT HIGH" in px.content_text(got["messages"][-1]["content"])
            assert "CONTEXT COMPACTED" not in text
        else:
            assert "CONTEXT COMPACTED" in text and "CONTEXT HIGH" not in text
            assert fwd_count(got) <= c - cfg.keep_margin + 200


def test_C1_pass_is_byte_identical(mkproxy, upstream):
    base, proxy, cfg, _ = mkproxy()
    raw = json.dumps({"model": "m", "messages": [{"role": "user", "content": "héllo  — spaced"}]},
                     ensure_ascii=False, indent=3).encode()
    fu.RECORDED.clear()
    httpx.post(base + "/v1/chat/completions", content=raw, headers={"content-type": "application/json"})
    assert fu.RECORDED[-1]["raw_len"] == len(raw)


def test_C2_tools_field_counted(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    tools = [{"type": "function", "function": {"name": f"t{i}", "description": W(390)}} for i in range(10)]
    msgs = history(cfg.warn_at - 3000)
    fu.RECORDED.clear()
    post(base, {"model": "m", "messages": msgs})
    assert "CONTEXT" not in all_text(last_fwd())
    post(base, {"model": "m", "messages": msgs, "tools": tools})
    assert "CONTEXT HIGH" in all_text(last_fwd()), "tool schemas were not counted"


def test_C4_list_and_image_content(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    msgs = history(cfg.compact_at + 2000)
    msgs[-1] = {"role": "user", "content": [{"type": "text", "text": W(300)},
                                            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]}
    r = post(base, {"model": "m", "messages": msgs})
    assert r.status_code == 200
    got = last_fwd()
    assert "CONTEXT COMPACTED" in all_text(got)
    assert got["messages"][-1]["content"][1]["type"] == "image_url"


def test_C5_tokenize_down_falls_back(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    fu.CTRL["tokenize"] = "down"
    msgs = history(8000)  # len//3 estimate of "w w w" text is ~2/3 token per word -> ~5.3k, pass
    r = post(base, {"model": "m", "messages": msgs})
    assert r.status_code == 200
    big = [msg("system", 100)] + [msg("user" if i % 2 == 0 else "assistant", 1000, word="abcdefgh") for i in range(15)]
    r = post(base, {"model": "m", "messages": big})
    assert r.status_code == 200
    assert "CONTEXT COMPACTED" in all_text(last_fwd())  # estimate (9 chars/3 = 3 per word) crossed compact
    ev = wait_events(cfg, 2)
    assert ev[-1]["tokenize_ok"] is False


def test_C6_tokenize_slow_bounded(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    fu.CTRL["tokenize"] = "slow"
    t = time.time()
    r = post(base, {"model": "m", "messages": history(3000)})
    assert r.status_code == 200
    assert time.time() - t < cfg.tokenize_timeout_s + 1.0


def test_C_bad_tokenize_reply(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    fu.CTRL["tokenize"] = "bad"
    assert post(base, {"model": "m", "messages": history(3000)}).status_code == 200


# ================================================================ COMPACTION

def test_K1_single_huge_tool_output_is_cut(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    msgs = [msg("system", 100), msg("user", 50)] + tool_pair(1, 30000)
    r = post(base, {"model": "m", "messages": msgs})
    assert r.status_code == 200
    got = last_fwd()
    assert "CUT BY CONTEXT PROXY" in all_text(got)
    assert fwd_count(got) < cfg.warn_at
    check_structure(got)


def test_K2_many_tool_pairs_never_split(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    msgs = [msg("system", 100), msg("user", 60)]
    for i in range(35):
        msgs += tool_pair(i, 520)
    post(base, {"model": "m", "messages": msgs})
    got = last_fwd()
    assert "CONTEXT COMPACTED" in all_text(got)
    check_structure(got)
    assert got["messages"][1]["role"] == "user"  # the turn's user message is pinned


def test_K3_parallel_tool_calls_kept_whole(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    msgs = [msg("system", 100), msg("user", 60)]
    for i in range(12):
        msgs += tool_pair(i, 500, n_calls=3)
    post(base, {"model": "m", "messages": msgs})
    got = last_fwd()
    assert "CONTEXT COMPACTED" in all_text(got)
    check_structure(got)


def test_K4_huge_last_user_message(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    msgs = history(12000) + [msg("assistant", 20), msg("user", 30000)]
    r = post(base, {"model": "m", "messages": msgs})
    assert r.status_code == 200
    got = last_fwd()
    last = got["messages"][-1]
    assert last["role"] == "user" and "CUT BY CONTEXT PROXY" in last["content"]
    assert fwd_count(got) < cfg.hard_max


def test_K5_no_system_message(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    msgs = history(cfg.compact_at + 800)[1:]
    post(base, {"model": "m", "messages": msgs})
    got = last_fwd()
    assert got["messages"][0]["role"] == "system"
    assert got["messages"][0]["content"].startswith("CONTEXT COMPACTED")
    check_structure(got)


def test_K6_K7_one_note_only(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    msgs = history(cfg.warn_at + 500)
    for _ in range(3):
        post(base, {"model": "m", "messages": msgs})
        assert all_text(last_fwd()).count("CONTEXT HIGH") == 1
    msgs += [msg("assistant", 500), msg("user", cfg.compact_at - cfg.warn_at)]
    post(base, {"model": "m", "messages": msgs})
    t = all_text(last_fwd())
    assert t.count("CONTEXT COMPACTED") == 1 and "CONTEXT HIGH" not in t


def test_X14_recompact_keeps_single_note(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    msgs = [msg("system", 100), msg("user", 60)]
    for i in range(60):
        msgs += tool_pair(i, 800)
        post(base, {"model": "m", "messages": msgs})
        assert all_text(last_fwd()).count("CONTEXT COMPACTED") <= 1
    assert sum(1 for e in events(cfg) if e.get("action") == "compact") >= 2


# ================================================================ STICKY / CACHE / THRASH

def test_T6_sticky_prefix_after_compaction(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    msgs = [msg("system", 100), msg("user", 60)]
    i = 0
    while fwd_count({"messages": msgs}) < cfg.compact_at:
        msgs += tool_pair(i, 700)
        i += 1
    post(base, {"model": "m", "messages": msgs})
    first = last_fwd()
    assert "CONTEXT COMPACTED" in all_text(first)
    prev = first
    for k in range(5):
        msgs += tool_pair(100 + k, 150)
        post(base, {"model": "m", "messages": msgs})
        cur = last_fwd()
        assert cur["messages"][0] == first["messages"][0], "system+note changed"
        assert cur["messages"][:len(prev["messages"]) - 1] == prev["messages"][:-1], "prefix changed"
        prev = cur
    acts = [e["action"] for e in wait_events(cfg, 6)]
    assert acts.count("compact") == 1 and acts[-5:] == ["sticky"] * 5


def test_K8_soak_no_thrash_no_overflow(mkproxy):
    """200-step agent loop the way Open WebUI sends it: full history every time."""
    base, proxy, cfg, _ = mkproxy()
    rng = random.Random(7)
    msgs = [msg("system", 300), msg("user", 80)]
    prev, compactions, since = None, 0, []
    last_c = 0
    for step in range(200):
        if step and step % 40 == 0:
            msgs += [msg("assistant", 60), msg("user", 40)]
        size = rng.choice([80, 150, 300, 600, 900, 1400, 2500, 6000])
        msgs += tool_pair(step, size, n_calls=rng.choice([1, 1, 1, 2]))
        r = post(base, {"model": "m", "messages": msgs})
        assert r.status_code == 200
        cur = last_fwd()
        check_structure(cur)
        n = fwd_count(cur)
        assert n < cfg.hard_max
        assert n < cfg.compact_at + 150, f"step {step}: forwarded {n}"
        ev = wait_events(cfg, step + 1)
        assert len(ev) == step + 1
        if ev[-1]["action"] == "compact":
            compactions += 1
            since.append(step - last_c)
            last_c = step
        elif prev is not None:
            assert cur["messages"][:len(prev["messages"]) - 1] == prev["messages"][:-1], f"prefix broke at {step}"
        prev = cur
    print(f"\nsoak: {compactions} compactions in 200 steps, gaps {since[1:]}")
    assert compactions >= 5
    assert statistics.median(since[1:]) >= 3, since


# ================================================================ HANDOFF

def _compact_once(base, cfg, pairs=30, out=700):
    msgs = [msg("system", 100), msg("user", 60)]
    for i in range(pairs):
        msgs += tool_pair(i, out)
    fu.RECORDED.clear()
    r = post(base, {"model": "m", "messages": msgs})
    assert r.status_code == 200
    return msgs


def summary_calls():
    return [r for r in fu.RECORDED if r["headers"].get("x-ctxproxy-skip") == "1"]


def test_H0_fresh_resume_used_no_summary(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    _compact_once(base, cfg)
    t = all_text(last_fwd())
    assert "do edit 08" in t and "older stuff" not in t
    assert summary_calls() == []


def test_H1_missing_progress_auto_summary(mkproxy):
    base, proxy, cfg, _ = mkproxy(progress=None)
    _compact_once(base, cfg)
    calls = summary_calls()
    assert len(calls) == 1
    assert calls[0]["body"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "Auto-summary" in all_text(last_fwd()) and "NEXT ACTION: do step 2" in all_text(last_fwd())


def test_H2_stale_resume_gets_summary_too(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    old = time.time() - 26 * 3600
    os.utime(cfg.progress_path, (old, old))
    _compact_once(base, cfg)
    t = all_text(last_fwd())
    assert len(summary_calls()) == 1
    assert "do edit 08" in t and "Auto-summary" in t


def test_H3_empty_resume_block(mkproxy):
    base, proxy, cfg, _ = mkproxy(progress="# PROGRESS\n\n## RESUME HERE\n\n## Log\n- x\n")
    _compact_once(base, cfg)
    assert len(summary_calls()) == 1


def test_H4_huge_resume_capped(mkproxy):
    base, proxy, cfg, _ = mkproxy(progress="## RESUME HERE\n" + ("x" * 200000) + "\n")
    _compact_once(base, cfg)
    sys_msg = last_fwd()["messages"][0]["content"]
    assert "handoff cut at 6000" in sys_msg
    assert len(sys_msg) < 100 * 4 + 6000 + 1500


def test_H5_half_written_file(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    stop = threading.Event()

    def writer():
        i = 0
        while not stop.is_set():
            with open(cfg.progress_path, "w") as f:  # deliberately not atomic
                f.write("## RESUME HERE\n")
                f.flush()
                f.write(f"- next action: edit {i}\n" * 2000)
            i += 1

    th = threading.Thread(target=writer, daemon=True)
    th.start()
    try:
        for k in range(10):
            msgs = [msg("system", 100), msg("user", 60 + k)]
            for i in range(30):
                msgs += tool_pair(i, 700)
            r = post(base, {"model": "m", "messages": msgs})
            assert r.status_code == 200
            assert "CONTEXT COMPACTED" in all_text(last_fwd())
    finally:
        stop.set()
        th.join()


def test_H6_invalid_utf8(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    with open(cfg.progress_path, "ab") as f:
        f.write(b"\xff\xfe broken bytes\n")
    with open(cfg.progress_path, "r+b") as f:
        data = f.read().replace(b"do edit 08.", b"do edit 08. \xff\xfe")
        f.seek(0)
        f.write(data)
    _compact_once(base, cfg)
    assert "do edit 08" in all_text(last_fwd())


@pytest.mark.parametrize("mode", ["500", "empty", "slow"])
def test_H7_H8_summary_failures(mkproxy, mode):
    base, proxy, cfg, _ = mkproxy(progress=None)
    fu.CTRL["summary"] = mode
    t = time.time()
    _compact_once(base, cfg)
    assert time.time() - t < cfg.summary_timeout_s + 3
    t_all = all_text(last_fwd())
    assert "CONTEXT COMPACTED" in t_all and "No handoff available" in t_all


def test_H9_summary_input_capped(mkproxy):
    base, proxy, cfg, _ = mkproxy(progress=None, summary_input_tokens=5000)
    _compact_once(base, cfg, pairs=60, out=900)
    body = summary_calls()[0]["body"]
    assert fwd_count(body) < 5000 + 200


# ================================================================ PROXY

def test_P1_streaming_passthrough(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    fu.CTRL.update(chunks=20, chunk_delay=0.1)
    t0 = time.time()
    first, lines = None, []
    with httpx.stream("POST", base + "/v1/chat/completions",
                      json={"model": "m", "stream": True, "messages": history(2000)}, timeout=30) as r:
        assert "text/event-stream" in r.headers["content-type"]
        for line in r.iter_lines():
            if line.startswith("data:"):
                if first is None:
                    first = time.time() - t0
                lines.append(line)
    assert first < 0.5
    assert [json.loads(line[5:])["choices"][0]["delta"].get("content") for line in lines[:20]] == [f"c{i} " for i in range(20)]
    assert lines[-1] == "data: [DONE]"
    ev = wait_events(cfg, 1)
    assert ev[-1]["up_prompt_n"] is not None and ev[-1]["up_predicted_n"] == 7


def test_P2_client_disconnect_closes_upstream(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    fu.CTRL.update(chunks=100, chunk_delay=0.1)
    with httpx.stream("POST", base + "/v1/chat/completions",
                      json={"model": "m", "stream": True, "messages": history(2000)}, timeout=30) as r:
        for i, _line in enumerate(r.iter_lines()):
            if i > 4:
                break
    t = time.time()
    while fu.STREAMS["cancelled"] == 0 and time.time() - t < 5:
        time.sleep(0.05)
    assert fu.STREAMS["cancelled"] == 1, fu.STREAMS
    fu.CTRL.update(chunks=3, chunk_delay=0)
    assert post(base, {"model": "m", "messages": history(500)}).status_code == 200
    assert any(e.get("error") == "client_gone" for e in wait_events(cfg, 1))


def test_P3_upstream_dies_mid_stream(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    fu.CTRL.update(chunks=50, chunk_delay=0.05, die_after=5)
    t = time.time()
    got = []
    with httpx.stream("POST", base + "/v1/chat/completions",
                      json={"model": "m", "stream": True, "messages": history(500)}, timeout=30) as r:
        for line in r.iter_lines():
            got.append(line)
    assert time.time() - t < 5
    assert any("stream broke" in g for g in got)
    fu.CTRL.update(die_after=None, chunks=2, chunk_delay=0)
    assert post(base, {"model": "m", "messages": history(500)}).status_code == 200


def test_P3b_upstream_down(mkproxy):
    base, proxy, cfg, _ = mkproxy(upstream=f"http://127.0.0.1:{free_port()}")
    t = time.time()
    r = post(base, {"model": "m", "messages": history(500)})
    assert r.status_code == 502 and "upstream unreachable" in r.text
    assert time.time() - t < 3
    assert httpx.get(base + "/v1/models").status_code == 502


def test_P4_concurrent_requests(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    fu.CTRL.update(chunks=10, chunk_delay=0.05)
    results = []

    def one(k):
        body = {"model": "m", "stream": True, "messages": history(3000 + k * 5000)}
        with httpx.stream("POST", base + "/v1/chat/completions", json=body, timeout=30) as r:
            results.append((r.status_code, sum(1 for _ in r.iter_lines())))

    ths = [threading.Thread(target=one, args=(k,)) for k in range(4)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    assert len(results) == 4 and all(s == 200 and n >= 11 for s, n in results)


def test_P5_total_timeout_scaled(mkproxy):
    base, proxy, cfg, _ = mkproxy(total_timeout_s=1.0)
    fu.CTRL.update(chunks=40, chunk_delay=0.1)
    t = time.time()
    with httpx.stream("POST", base + "/v1/chat/completions",
                      json={"model": "m", "stream": True, "messages": history(500)}, timeout=30) as r:
        lines = list(r.iter_lines())
    assert time.time() - t < 2.5
    assert any("s limit" in line for line in lines)


def test_X8_long_silence_survives(mkproxy):
    base, proxy, cfg, _ = mkproxy(read_timeout_s=5.0)
    fu.CTRL.update(silence_before=2.0, chunks=3)
    with httpx.stream("POST", base + "/v1/chat/completions",
                      json={"model": "m", "stream": True, "messages": history(500)}, timeout=30) as r:
        lines = [line for line in r.iter_lines() if line]
    assert lines[-1] == "data: [DONE]"


def test_P6_non_chat_endpoints_identical(mkproxy, upstream):
    base, proxy, cfg, _ = mkproxy()
    for path in ["/v1/models", "/props", "/health"]:
        a, b = httpx.get(upstream + path), httpx.get(base + path)
        assert (a.status_code, a.content) == (b.status_code, b.content)
    a = httpx.post(upstream + "/tokenize", json={"content": "a b c"})
    b = httpx.post(base + "/tokenize", json={"content": "a b c"})
    assert a.content == b.content


def test_P7_big_bodies(mkproxy, upstream):
    base, proxy, cfg, _ = mkproxy(max_body_bytes=30 * 1024 * 1024)
    blob = "x" * (10 * 1024 * 1024)
    r = httpx.post(base + "/echo", content=blob, timeout=60)
    assert r.json()["len"] == len(blob)
    msgs = [msg("system", 50), {"role": "user", "content": W(2_000_000)}]
    r = post(base, {"model": "m", "messages": msgs})
    assert r.status_code == 200 and "CUT BY CONTEXT PROXY" in all_text(last_fwd())
    r = httpx.post(base + "/echo", content="y" * (31 * 1024 * 1024), timeout=60)
    assert r.status_code == 413


def test_P8_auth_passthrough_and_client_key(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    r = httpx.post(base + "/echo", content=b"{}", headers={"Authorization": "Bearer testkey123", "X-Custom": "v"})
    assert r.json() == {"len": 2, "auth": "Bearer testkey123", "custom": "v"}
    base2, _, _, _ = mkproxy(client_key="sekrit", upstream_key="upkey")
    assert httpx.post(base2 + "/echo", content=b"{}").status_code == 401
    r = httpx.post(base2 + "/echo", content=b"{}", headers={"Authorization": "Bearer sekrit"})
    assert r.json()["auth"] == "Bearer upkey"


def test_P9_restart_keeps_sticky_state(mkproxy, tmp_path):
    base, proxy, cfg, srv = mkproxy()
    msgs = _compact_once(base, cfg)
    first_sys = last_fwd()["messages"][0]
    srv.stop()
    base2, proxy2, cfg2, _ = mkproxy()  # same tmp_path -> same state_dir
    msgs += tool_pair(999, 100)
    post(base2, {"model": "m", "messages": msgs})
    assert last_fwd()["messages"][0] == first_sys
    assert wait_events(cfg2, 2)[-1]["action"] == "sticky"


def test_P9b_corrupt_state_file(mkproxy, tmp_path):
    os.makedirs(tmp_path / "state", exist_ok=True)
    (tmp_path / "state" / "state.json").write_text("{not json")
    base, proxy, cfg, _ = mkproxy()
    _compact_once(base, cfg)
    assert "CONTEXT COMPACTED" in all_text(last_fwd())


def test_P10_bind_before_address_exists():
    s = px.make_socket("172.31.254.254", free_port())
    s.close()


def test_edited_history_invalidates_sticky(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    msgs = _compact_once(base, cfg)
    msgs[5] = dict(msgs[5], content=W(700, "edited"))  # an earlier message changed
    msgs += tool_pair(500, 100)
    r = post(base, {"model": "m", "messages": msgs})
    assert r.status_code == 200
    got = last_fwd()
    check_structure(got)
    assert "edited" not in all_text(got) or "CONTEXT COMPACTED" in all_text(got)


def test_same_opener_new_chat_not_confused(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    _compact_once(base, cfg)
    small = [msg("system", 100), msg("user", 60)] + tool_pair(0, 50)
    fu.RECORDED.clear()
    post(base, {"model": "m", "messages": small})
    assert last_fwd()["messages"] == small


# ================================================================ SKIP / SAFETY

def test_skip_task_requests_and_header(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    big = history(cfg.compact_at + 2000)
    task = big[:-1] + [{"role": "user", "content": "### Task:\nGenerate a title " + W(50)}]
    post(base, {"model": "m", "messages": task})
    assert last_fwd()["messages"] == task
    post(base, {"model": "m", "messages": big}, headers={"X-Ctxproxy-Skip": "1"})
    assert fu.RECORDED[-1]["body"]["messages"] == big
    assert "x-ctxproxy-skip" not in {k for k in fu.RECORDED[-1]["headers"]}
    assert [e["action"] for e in wait_events(cfg, 2)] == ["skip", "skip"]


def test_F1_no_text_or_secrets_in_events(mkproxy):
    base, proxy, cfg, _ = mkproxy(progress=None)
    canary = "SECRETCANARY9x"
    msgs = [msg("system", 100, word=canary), msg("user", 60, word=canary)]
    for i in range(30):
        msgs += tool_pair(i, 700)
    post(base, {"model": "m", "messages": msgs}, headers={"Authorization": "Bearer " + canary})
    post(base, {"model": "m", "messages": [msg("user", 5, word=canary)]})
    wait_events(cfg, 2)
    raw = open(os.path.join(cfg.state_dir, "events.jsonl")).read()
    assert canary not in raw and "do step 2" not in raw


def test_F2_events_rotate(mkproxy):
    base, proxy, cfg, _ = mkproxy(events_max_bytes=2000)
    for _ in range(40):
        post(base, {"model": "m", "messages": [msg("user", 5)]})
    wait_events(cfg, 1)
    p = os.path.join(cfg.state_dir, "events.jsonl")
    assert os.path.getsize(p) < 4000 and os.path.exists(p + ".1")
    for line in open(p):
        json.loads(line)


def test_F3_latency_under_threshold(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    body = {"model": "m", "messages": history(12000, chunk=500)}
    for _ in range(50):
        post(base, body)
    ev = wait_events(cfg, 50)
    ms = sorted(e["ms_added"] for e in ev[1:])
    p95 = ms[int(len(ms) * 0.95) - 1]
    assert p95 < 50, p95


@pytest.mark.parametrize("fault", ["transform", "compact"])
def test_F4_fail_open(mkproxy, fault):
    base, proxy, cfg, _ = mkproxy(fault=fault)
    body = {"model": "m", "messages": history(cfg.compact_at + 500)}
    r = post(base, body)
    assert r.status_code == 200
    assert last_fwd() == body
    assert wait_events(cfg, 1)[-1]["action"] == "fail_open"


def test_too_large_even_after_cuts_is_clear_error(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    msgs = [msg("system", cfg.limit)] + [msg("user", 20)]
    r = post(base, {"model": "m", "messages": msgs})
    assert r.status_code == 400 and "too large" in r.text
    assert fu.RECORDED == []


def test_X2_regenerate_same_body_same_result(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    msgs = _compact_once(base, cfg)
    a = last_fwd()
    post(base, {"model": "m", "messages": msgs})
    assert last_fwd() == a


def test_X12_multibyte_cut_is_valid(mkproxy):
    base, proxy, cfg, _ = mkproxy()
    blob = ("é😀 " * 20000) + "x" * 50000
    msgs = [msg("system", 50), msg("user", 20)] + [{"role": "assistant", "content": "",
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "r", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": blob}]
    r = post(base, {"model": "m", "messages": msgs})
    assert r.status_code == 200
    out = last_fwd()["messages"][-1]["content"]
    out.encode("utf-8")
    assert "CUT BY CONTEXT PROXY" in out


# ================================================================ NEW CHAT START note (resume) + git facts

import subprocess  # noqa: E402


@pytest.fixture
def gitrepo(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()

    def g(*a):
        subprocess.run(["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                       check=True, capture_output=True)
    g("init", "-q")
    (d / "a.txt").write_text("a\n")
    g("add", "-A")
    g("commit", "-q", "-m", "first commit SUBJECTONE")
    (d / "b.txt").write_text("b\n")
    g("add", "b.txt")
    g("commit", "-q", "-m", "second commit SUBJECTTWO")
    (d / "dirty.txt").write_text("x\n")
    return d


def sys_text(body):
    return px.content_text(body["messages"][0]["content"])


def test_R1_new_chat_gets_note(mkproxy, gitrepo):
    base, proxy, cfg, _ = mkproxy(resume_new_chats=True, git_dir=str(gitrepo))
    body = {"model": "m", "messages": [msg("system", 100), msg("user", 20)]}
    fu.RECORDED.clear()
    assert post(base, body).status_code == 200
    got = last_fwd()
    t = sys_text(got)
    assert t.startswith(body["messages"][0]["content"] + "\n\nNEW CHAT START")
    assert "do edit 08" in t and "older stuff" not in t
    assert "SUBJECTTWO" in t and "SUBJECTONE" in t and "?? dirty.txt" in t
    assert got["messages"][1:] == body["messages"][1:]
    ev = wait_events(cfg, 1)[-1]
    assert ev["action"] == "resume" and ev["resume"] == "new" and ev["resume_tokens"] > 50
    assert ev["tok_after"] == fwd_count(got), "the note must be counted"
    raw = open(os.path.join(cfg.state_dir, "events.jsonl")).read()
    assert "SUBJECT" not in raw and "edit 08" not in raw


def test_R2_note_frozen_for_the_whole_chat(mkproxy, gitrepo):
    base, proxy, cfg, _ = mkproxy(resume_new_chats=True, git_dir=str(gitrepo))
    msgs = [msg("system", 100), msg("user", 20)]
    post(base, {"model": "m", "messages": msgs})
    first = last_fwd()["messages"][0]
    (gitrepo / "later.txt").write_text("changed after the chat started\n")
    for i in range(3):
        msgs += tool_pair(i, 50)
        post(base, {"model": "m", "messages": msgs})
        cur = last_fwd()
        assert cur["messages"][0] == first
        assert cur["messages"][1:] == msgs[1:]
    acts = [(e["action"], e.get("resume")) for e in wait_events(cfg, 4)]
    assert acts == [("resume", "new")] + [("resume", "sticky")] * 3


def test_R3_same_opener_later_chat_does_not_swap_note(mkproxy, gitrepo):
    base, proxy, cfg, _ = mkproxy(resume_new_chats=True, git_dir=str(gitrepo))
    opener = [msg("system", 100), msg("user", 20)]
    a = list(opener)
    post(base, {"model": "m", "messages": a})
    note_a = last_fwd()["messages"][0]
    a += tool_pair(0, 30)
    post(base, {"model": "m", "messages": a})
    (gitrepo / "between.txt").write_text("x\n")
    b = list(opener)
    post(base, {"model": "m", "messages": b})
    note_b = last_fwd()["messages"][0]
    assert note_b != note_a and "between.txt" in px.content_text(note_b["content"])
    a += tool_pair(1, 30)
    post(base, {"model": "m", "messages": a})
    assert last_fwd()["messages"][0] == note_a
    b += tool_pair(5, 30)
    post(base, {"model": "m", "messages": b})
    assert last_fwd()["messages"][0] == note_b


def test_R4_opt_out_header_and_config_off(mkproxy, gitrepo):
    base, proxy, cfg, _ = mkproxy(resume_new_chats=True, git_dir=str(gitrepo))
    body = {"model": "m", "messages": [msg("system", 100), msg("user", 20)]}
    post(base, body, headers={"X-Ctxproxy-No-Resume": "1"})
    assert fu.RECORDED[-1]["body"] == body
    assert "x-ctxproxy-no-resume" not in fu.RECORDED[-1]["headers"]
    base2, _, cfg2, _ = mkproxy(resume_new_chats=False, git_dir=str(gitrepo))
    post(base2, body)
    assert last_fwd() == body


def test_R5_chat_older_than_the_proxy_is_left_alone(mkproxy, gitrepo):
    base, proxy, cfg, _ = mkproxy(resume_new_chats=True, git_dir=str(gitrepo))
    msgs = [msg("system", 100), msg("user", 20)] + tool_pair(0, 30)
    post(base, {"model": "m", "messages": msgs})
    assert last_fwd()["messages"] == msgs
    assert wait_events(cfg, 1)[-1]["action"] == "pass"


def test_R6_compaction_replaces_note_and_has_git_facts(mkproxy, gitrepo):
    base, proxy, cfg, _ = mkproxy(resume_new_chats=True, git_dir=str(gitrepo))
    msgs = [msg("system", 100), msg("user", 60)]
    post(base, {"model": "m", "messages": msgs})
    i = 0
    while True:
        msgs += tool_pair(i, 700)
        i += 1
        post(base, {"model": "m", "messages": msgs})
        if wait_events(cfg, i + 1)[-1]["action"] == "compact":
            break
        assert i < 60
    got = last_fwd()
    t = all_text(got)
    check_structure(got)
    assert t.count("CONTEXT COMPACTED") == 1 and "NEW CHAT START" not in t
    assert "SUBJECTTWO" in t and "?? dirty.txt" in t and "do edit 08" in t
    assert events(cfg)[-1]["resume"] == "replaced"
    msgs += tool_pair(999, 50)
    post(base, {"model": "m", "messages": msgs})
    assert last_fwd()["messages"][0] == got["messages"][0]
    assert "NEW CHAT START" not in all_text(last_fwd())


def test_R7_git_unavailable_still_works(mkproxy, tmp_path):
    notrepo = tmp_path / "notrepo"
    notrepo.mkdir()
    for d in (str(notrepo), str(tmp_path / "missing")):
        base, proxy, cfg, _ = mkproxy(resume_new_chats=True, git_dir=d)
        body = {"model": "m", "messages": [msg("system", 100), msg("user", 20, word=os.path.basename(d))]}
        assert post(base, body).status_code == 200
        t = sys_text(last_fwd())
        assert "NEW CHAT START" in t and "unavailable" in t and "do edit 08" in t


def test_R8_restart_keeps_the_note(mkproxy, gitrepo):
    base, proxy, cfg, srv = mkproxy(resume_new_chats=True, git_dir=str(gitrepo))
    msgs = [msg("system", 100), msg("user", 20)]
    post(base, {"model": "m", "messages": msgs})
    first = last_fwd()["messages"][0]
    srv.stop()
    (gitrepo / "after-restart.txt").write_text("x\n")
    base2, proxy2, cfg2, _ = mkproxy(resume_new_chats=True, git_dir=str(gitrepo))
    msgs += tool_pair(0, 30)
    post(base2, {"model": "m", "messages": msgs})
    assert last_fwd()["messages"][0] == first
    assert wait_events(cfg2, 2)[-1]["resume"] == "sticky"


def test_R9_no_system_message_gets_one(mkproxy, gitrepo):
    base, proxy, cfg, _ = mkproxy(resume_new_chats=True, git_dir=str(gitrepo))
    body = {"model": "m", "messages": [msg("user", 20)]}
    post(base, body)
    got = last_fwd()
    assert got["messages"][0]["role"] == "system" and "NEW CHAT START" in sys_text(got)
    assert got["messages"][1:] == body["messages"]


def test_R10_missing_progress_file(mkproxy, gitrepo):
    base, proxy, cfg, _ = mkproxy(progress=None, resume_new_chats=True, git_dir=str(gitrepo))
    post(base, {"model": "m", "messages": [msg("system", 100), msg("user", 20)]})
    t = sys_text(last_fwd())
    assert "No RESUME HERE block found" in t and "SUBJECTTWO" in t


def test_R11_note_counts_toward_warn(mkproxy, gitrepo):
    base, proxy, cfg, _ = mkproxy(resume_new_chats=True, git_dir=str(gitrepo))
    body = {"model": "m", "messages": [msg("system", cfg.warn_at - 70), msg("user", 20)]}
    assert fwd_count(body) < cfg.warn_at
    post(base, body)
    got = last_fwd()
    assert "NEW CHAT START" in sys_text(got)
    assert "CONTEXT HIGH" in px.content_text(got["messages"][-1]["content"])
    ev = wait_events(cfg, 1)[-1]
    assert ev["warned"] and ev["action"] == "resume"


def test_R12_task_requests_still_skipped(mkproxy, gitrepo):
    base, proxy, cfg, _ = mkproxy(resume_new_chats=True, git_dir=str(gitrepo))
    body = {"model": "m", "messages": [msg("system", 50), {"role": "user", "content": "### Task:\nMake a title"}]}
    post(base, body)
    assert last_fwd() == body
    assert wait_events(cfg, 1)[-1]["action"] == "skip"
