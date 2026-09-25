"""A fake llama-server for the proxy tests. 1 token = 1 whitespace-separated word.

Behaviour is switched per test through the shared CTRL dict; every chat request
is recorded in RECORDED (body + headers) for the test to inspect.
"""
import asyncio
import json
import time

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

CTRL = {}
RECORDED = []
STREAMS = {"started": 0, "finished": 0, "cancelled": 0}


def reset():
    CTRL.clear()
    CTRL.update({
        "tokenize": "ok",        # ok | down | slow | bad
        "tokenize_delay": 4.0,
        "summary": "ok",         # ok | 500 | slow | empty
        "summary_text": "GOAL: test goal. DONE: step 1 (commit abc1234). NEXT ACTION: do step 2. OPEN PROBLEMS: none.",
        "summary_delay": 3.0,
        "chunks": 5,
        "chunk_delay": 0.0,
        "silence_before": 0.0,
        "die_after": None,       # int: drop the connection after this many chunks
        "status": 200,
    })
    RECORDED.clear()
    for k in STREAMS:
        STREAMS[k] = 0


reset()


async def tokenize(request: Request):
    mode = CTRL["tokenize"]
    if mode == "down":
        return JSONResponse({"error": "down"}, status_code=500)
    if mode == "slow":
        await asyncio.sleep(CTRL["tokenize_delay"])
    if mode == "bad":
        return JSONResponse({"nope": 1})
    body = await request.json()
    n = len(str(body.get("content", "")).split())
    return JSONResponse({"tokens": list(range(n))})


def _usage(n_prompt):
    return {"timings": {"prompt_n": n_prompt, "cache_n": 0, "predicted_n": 7, "prompt_ms": 1.0},
            "usage": {"prompt_tokens": n_prompt, "completion_tokens": 7}}


async def chat(request: Request):
    raw = await request.body()
    body = json.loads(raw)
    headers = {k.lower(): v for k, v in request.headers.items()}
    RECORDED.append({"body": body, "headers": headers, "raw_len": len(raw), "t": time.time()})
    if headers.get("x-ctxproxy-skip") == "1" and body.get("max_tokens") == 800 and body.get("stream") is False:
        mode = CTRL["summary"]
        if mode == "500":
            return JSONResponse({"error": "boom"}, status_code=500)
        if mode == "slow":
            await asyncio.sleep(CTRL["summary_delay"])
        text = "" if mode == "empty" else CTRL["summary_text"]
        return JSONResponse({"choices": [{"message": {"role": "assistant", "content": text}}]})
    if CTRL["status"] != 200:
        return JSONResponse({"error": "status"}, status_code=CTRL["status"])
    n_prompt = sum(len(json.dumps(m).split()) for m in body.get("messages", []))
    if not body.get("stream"):
        d = {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
        d.update(_usage(n_prompt))
        return JSONResponse(d)

    async def gen():
        STREAMS["started"] += 1
        try:
            if CTRL["silence_before"]:
                await asyncio.sleep(CTRL["silence_before"])
            for i in range(CTRL["chunks"]):
                if CTRL["die_after"] is not None and i == CTRL["die_after"]:
                    raise RuntimeError("upstream died")
                yield ("data: " + json.dumps({"choices": [{"delta": {"content": f"c{i} "}}]}) + "\n\n").encode()
                if CTRL["chunk_delay"]:
                    await asyncio.sleep(CTRL["chunk_delay"])
            last = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
            last.update(_usage(n_prompt))
            yield ("data: " + json.dumps(last) + "\n\n").encode()
            yield b"data: [DONE]\n\n"
            STREAMS["finished"] += 1
        except (asyncio.CancelledError, GeneratorExit):
            STREAMS["cancelled"] += 1
            raise

    return StreamingResponse(gen(), media_type="text/event-stream")


async def models(request: Request):
    return JSONResponse({"object": "list", "data": [{"id": "jarvis", "object": "model"}]})


async def props(request: Request):
    return JSONResponse({"n_ctx": 24576, "echo_auth": request.headers.get("authorization")})


async def health(request: Request):
    return JSONResponse({"status": "ok"})


async def echo(request: Request):
    raw = await request.body()
    return JSONResponse({"len": len(raw), "auth": request.headers.get("authorization"),
                         "custom": request.headers.get("x-custom")})


app = Starlette(routes=[
    Route("/tokenize", tokenize, methods=["POST"]),
    Route("/v1/chat/completions", chat, methods=["POST"]),
    Route("/v1/models", models, methods=["GET"]),
    Route("/props", props, methods=["GET"]),
    Route("/health", health, methods=["GET"]),
    Route("/echo", echo, methods=["POST"]),
])
