#!/usr/bin/env python3
"""A-real checks: the proxy against the REAL llama-server (read-only for the box).

Starts its own proxy on 127.0.0.1:8113 (temp state dir), runs 8 checks, stops it.
Uses enable_thinking=false and max_tokens 4, so each request is short; the long
part is llama-server reading ~17k-token prompts (about 1-2 minutes in total).

Run:  ~/jarvis-build/venv/bin/python ~/jarvis-build/ctxproxy/smoke_real.py
"""
import json
import os
import sys
import tempfile
import threading
import time

import httpx
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proxy as px  # noqa: E402

UP = os.environ.get("CTXPROXY_UPSTREAM", "http://127.0.0.1:8080")
PORT = 8113
BASE = f"http://127.0.0.1:{PORT}"
SRC = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy.py"), encoding="utf-8").read()
results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


def text_block(i, n_chars):
    start = (i * 997) % max(1, len(SRC) - n_chars)
    return SRC[start:start + n_chars]


def pair(i, n_chars):
    cid = f"call_{i}"
    return [{"role": "assistant", "content": "",
             "tool_calls": [{"id": cid, "type": "function",
                             "function": {"name": "read_file", "arguments": json.dumps({"path": f"/tmp/f{i}.py"})}}]},
            {"role": "tool", "tool_call_id": cid, "content": text_block(i, n_chars)}]


def main():
    tmp = tempfile.mkdtemp(prefix="ctxsmoke-")
    prog = os.path.join(tmp, "PROGRESS.md")
    with open(prog, "w") as f:
        f.write("# PROGRESS\n\n## RESUME HERE\n- Smoke test. Exact next action: none.\n")
    cfg = px.Config(host="127.0.0.1", port=PORT, upstream=UP, state_dir=tmp, progress_path=prog,
                    resume_new_chats=True)
    app = px.build_app(cfg)
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    t_start = time.time()
    while not srv.started:
        if not th.is_alive() or time.time() - t_start > 20:
            print(f"FAIL  the test proxy could not start on 127.0.0.1:{PORT} (port already in use?). "
                  f"Check: ss -ltnp | grep :{PORT}")
            sys.exit(2)
        time.sleep(0.05)
    print(f"proxy on {BASE} -> {UP}; warn {cfg.warn_at}, compact {cfg.compact_at}; state in {tmp}")
    c = httpx.Client(timeout=600)
    try:
        # 1. passthrough
        a, b = c.get(UP + "/v1/models"), c.get(BASE + "/v1/models")
        check("P6 /v1/models identical through proxy", a.status_code == b.status_code == 200 and a.json() == b.json())
        model = a.json()["data"][0]["id"]
        opts = {"model": model, "max_tokens": 4, "temperature": 0,
                "chat_template_kwargs": {"enable_thinking": False}}

        def send(msgs, stream=False, resume=False):
            body = dict(opts, messages=msgs, stream=stream)
            hdrs = {} if resume else {"X-Ctxproxy-No-Resume": "1"}  # checks 1-5 measure the proxy without it
            if stream:
                lines = []
                with c.stream("POST", BASE + "/v1/chat/completions", json=body, headers=hdrs) as r:
                    for line in r.iter_lines():
                        lines.append(line)
                return r.status_code, lines
            r = c.post(BASE + "/v1/chat/completions", json=body, headers=hdrs)
            return r.status_code, r.json()

        def last_event():
            time.sleep(0.3)
            with open(os.path.join(tmp, "events.jsonl")) as f:
                return json.loads(f.readlines()[-1])

        # 2. streaming
        st, lines = send([{"role": "user", "content": "Say hi."}], stream=True)
        check("P1 streaming through proxy", st == 200 and any(x.strip() == "data: [DONE]" for x in lines))

        # 3. calibration: our count vs llama-server's prompt size, 3 shapes
        sysmsg = {"role": "system", "content": "You are Jarvis Builder. " + text_block(99, 1500)}
        shapes = [
            [sysmsg, {"role": "user", "content": text_block(1, 6000)}],
            [sysmsg, {"role": "user", "content": "read files"}] + pair(2, 3000) + pair(3, 3000),
            [sysmsg, {"role": "user", "content": "héllo — ünïcode ✓ " * 200}],
        ]
        gaps = []
        for i, msgs in enumerate(shapes):
            st, _ = send(msgs)
            ev = last_event()
            real = (ev.get("up_prompt_n") or 0) + (ev.get("up_cache_n") or 0)
            ours = ev.get("tok_after") or ev.get("tok_before")
            if st == 200 and real:
                gaps.append((ours - real) / real * 100)
                print(f"      shape {i}: ours {ours}, llama-server {real}, gap {gaps[-1]:+.1f}%")
            else:
                print(f"      shape {i}: status {st}, event {ev}")
        check("C3 count within 5% of llama-server (3 shapes)", len(gaps) == 3 and all(abs(g) < 5 for g in gaps),
              "gaps: " + ", ".join(f"{g:+.1f}%" for g in gaps))

        # 4. warn note appended to a tool message: template accepts it
        msgs = [sysmsg, {"role": "user", "content": "Do the task."}]
        i = 10
        while True:
            msgs += pair(i, 2400)
            i += 1
            st, _ = send(msgs)
            ev = last_event()
            if ev.get("action") in ("warn", "compact") or ev.get("warned") or st != 200:
                break
        check("warn band: request accepted by llama-server", st == 200 and ev.get("warned"),
              f"tokens {ev.get('tok_after')}, action {ev.get('action')}")

        # 5. compaction + sticky cache
        while ev.get("action") != "compact" and st == 200:
            msgs += pair(i, 2400)
            i += 1
            st, _ = send(msgs)
            ev = last_event()
        check("compaction: compacted request accepted by llama-server (template OK)", st == 200 and ev.get("action") == "compact",
              f"{ev.get('tok_before')} -> {ev.get('tok_after')} tokens")
        first_total = (ev.get("up_prompt_n") or 0) + (ev.get("up_cache_n") or 0)
        evals = []
        for k in range(4):
            msgs += pair(i, 600)
            i += 1
            st, _ = send(msgs)
            e = last_event()
            evals.append((e.get("action"), e.get("up_prompt_n"), e.get("up_cache_n")))
        print("      after compaction (action, evaluated, reused):", evals)
        ok = all(a == "sticky" for a, _, _ in evals) and all(
            p is not None and first_total and p < 0.25 * first_total for _, p, _ in evals)
        check("M1 sticky prefix: next 4 requests reuse the cache (<25% re-read)", ok)

        # 6. new-chat note (RESUME HERE + git facts from ~/jarvis-build): accepted, then reused
        chat = [sysmsg, {"role": "user", "content": "Smoke test: say OK."}]
        st, _ = send(chat, resume=True)
        e1 = last_event()
        chat += [{"role": "assistant", "content": "OK."}, {"role": "user", "content": "Say OK again."}]
        st2, _ = send(chat, resume=True)
        e2 = last_event()
        total2 = (e2.get("up_prompt_n") or 0) + (e2.get("up_cache_n") or 0)
        print(f"      new chat: note {e1.get('resume_tokens')} tokens, {e1.get('tok_before')} -> "
              f"{e1.get('tok_after')}; next request re-read {e2.get('up_prompt_n')} of {total2}")
        check("R1 new-chat note accepted by llama-server", st == 200 and e1.get("resume") == "new",
              f"action {e1.get('action')}")
        check("R2 next request of that chat keeps the note and reuses the cache",
              st2 == 200 and e2.get("resume") == "sticky" and total2 > 0
              and (e2.get("up_prompt_n") or 0) < 0.5 * total2)
    finally:
        srv.should_exit = True
        th.join(timeout=10)
    bad = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} passed" + (f"; FAILED: {bad}" if bad else ""))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
