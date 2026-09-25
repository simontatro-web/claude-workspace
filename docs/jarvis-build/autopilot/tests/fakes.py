"""Fakes for the autopilot tests: a scripted model server and an OpenAPI tool server.

The model server speaks the OpenAI chat API (streamed like llama-server, tool-call arguments split
across chunks) and also /tokenize (1 token = 1 word) so the real context proxy can sit in front of it.
The tool server really runs run_host_command in a temp folder, so git commits are real.
"""
import asyncio
import json
import os
import subprocess
import time

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

MODEL = {"script": None, "requests": [], "ntfy": [], "delay": 0.0}
TOOLS = {"calls": [], "workdir": "/tmp", "scheme": "bearer", "key": "toolkey"}


def reset():
    MODEL.update({"script": None, "requests": [], "ntfy": [], "delay": 0.0})
    TOOLS.update({"calls": [], "workdir": "/tmp", "scheme": "bearer", "key": "toolkey"})


# ---------------------------------------------------------------- model

def next_reply(body):
    sc = MODEL["script"]
    if callable(sc):
        return sc(body)
    if sc:
        return sc.pop(0)
    return {"content": "idle"}


def sse(obj):
    return ("data: " + json.dumps(obj) + "\n\n").encode()


async def chat(request: Request):
    body = await request.json()
    headers = {k.lower(): v for k, v in request.headers.items()}
    MODEL["requests"].append({"body": body, "headers": headers})
    if not body.get("stream"):
        return JSONResponse({"choices": [{"message": {"role": "assistant", "content": "OK"},
                                          "finish_reason": "stop"}]})
    if MODEL["delay"]:
        await asyncio.sleep(MODEL["delay"])
    r = next_reply(body)
    if r.get("error"):
        return JSONResponse({"error": {"message": "fake error"}}, status_code=r["error"])

    async def gen():
        if r.get("reasoning"):
            yield sse({"choices": [{"delta": {"reasoning_content": r["reasoning"]}}]})
        text = r.get("content") or ""
        for i in range(0, len(text), 7):
            yield sse({"choices": [{"delta": {"content": text[i:i + 7]}}]})
        for i, (name, args) in enumerate(r.get("tool_calls") or []):
            raw = args if isinstance(args, str) else json.dumps(args)
            half = len(raw) // 2
            yield sse({"choices": [{"delta": {"tool_calls": [{"index": i, "id": f"fc_{time.time_ns()}_{i}",
                                                              "type": "function",
                                                              "function": {"name": name, "arguments": raw[:half]}}]}}]})
            yield sse({"choices": [{"delta": {"tool_calls": [{"index": i, "function": {"arguments": raw[half:]}}]}}]})
        if r.get("break"):
            return
        finish = r.get("finish") or ("tool_calls" if r.get("tool_calls") else "stop")
        yield sse({"choices": [{"delta": {}, "finish_reason": finish}],
                   "timings": {"prompt_n": 10, "cache_n": 0, "predicted_n": 5}})
        yield b"data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


async def models(request: Request):
    return JSONResponse({"object": "list", "data": [{"id": "jarvis", "object": "model"}]})


async def tokenize(request: Request):
    body = await request.json()
    return JSONResponse({"tokens": list(range(len(str(body.get("content", "")).split())))})


async def health(request: Request):
    return JSONResponse({"ok": True, "compact_at": 17576, "resume_new_chats": True})


async def ntfy(request: Request):
    MODEL["ntfy"].append({"title": request.headers.get("title"), "body": (await request.body()).decode()})
    return JSONResponse({"ok": True})


model_app = Starlette(routes=[
    Route("/v1/chat/completions", chat, methods=["POST"]),
    Route("/v1/models", models, methods=["GET"]),
    Route("/tokenize", tokenize, methods=["POST"]),
    Route("/ctxproxy/health", health, methods=["GET"]),
    Route("/ntfy", ntfy, methods=["POST"]),
])


# ---------------------------------------------------------------- tool server

def spec():
    sec = ({"HTTPBearer": {"type": "http", "scheme": "bearer"}} if TOOLS["scheme"] == "bearer"
           else {"Key": {"type": "apiKey", "in": "header", "name": "X-Api-Key"}})
    return {
        "openapi": "3.1.0",
        "info": {"title": "fake tools", "version": "1"},
        "paths": {
            "/run_host_command": {"post": {"operationId": "run_host_command", "summary": "Run a shell command",
                                           "requestBody": {"content": {"application/json": {"schema": {
                                               "$ref": "#/components/schemas/CommandIn"}}}}}},
            "/write_file": {"post": {"operationId": "write_file", "description": "Write a file",
                                     "requestBody": {"content": {"application/json": {"schema": {
                                         "$ref": "#/components/schemas/WriteIn"}}}}}},
            "/list_tools": {"get": {"operationId": "list_tools", "summary": "List plugins"}},
            "/create_tool": {"post": {"operationId": "create_tool", "summary": "Add a plugin",
                                      "requestBody": {"content": {"application/json": {"schema": {
                                          "type": "object", "properties": {"name": {"type": "string"},
                                                                           "code": {"type": "string"}}}}}}}},
            "/items/{item_id}": {"get": {"operationId": "get_item", "summary": "Get an item",
                                         "parameters": [{"name": "item_id", "in": "path", "required": True,
                                                         "schema": {"type": "string"}},
                                                        {"name": "verbose", "in": "query",
                                                         "schema": {"type": "boolean"}}]}},
        },
        "components": {
            "schemas": {
                "CommandIn": {"type": "object", "properties": {"command": {"type": "string"}},
                              "required": ["command"]},
                "WriteIn": {"type": "object", "properties": {"path": {"type": "string"},
                                                             "content": {"type": "string"}},
                            "required": ["path", "content"]},
            },
            "securitySchemes": sec,
        },
    }


def authed(request):
    if TOOLS["scheme"] == "bearer":
        return request.headers.get("authorization") == "Bearer " + TOOLS["key"]
    return request.headers.get("x-api-key") == TOOLS["key"]


async def openapi(request: Request):
    return JSONResponse(spec())


async def run_cmd(request: Request):
    if not authed(request):
        return JSONResponse({"detail": "bad key"}, status_code=401)
    body = await request.json()
    TOOLS["calls"].append(("run_host_command", body))
    r = subprocess.run(body["command"], shell=True, cwd=TOOLS["workdir"], capture_output=True, text=True, timeout=60)
    return JSONResponse({"stdout": r.stdout[-4000:], "stderr": r.stderr[-4000:], "exit_code": r.returncode})


async def write_file(request: Request):
    if not authed(request):
        return JSONResponse({"detail": "bad key"}, status_code=401)
    body = await request.json()
    TOOLS["calls"].append(("write_file", body))
    with open(os.path.expanduser(body["path"]), "w") as f:
        f.write(body["content"])
    return JSONResponse({"ok": True})


async def list_tools(request: Request):
    if not authed(request):
        return JSONResponse({"detail": "bad key"}, status_code=401)
    TOOLS["calls"].append(("list_tools", {}))
    return JSONResponse({"plugins": ["gpu_status: loaded"]})


async def create_tool(request: Request):
    body = await request.json()
    TOOLS["calls"].append(("create_tool", body))
    return JSONResponse({"ok": True})


async def get_item(request: Request):
    TOOLS["calls"].append(("get_item", {"path": request.url.path, "query": str(request.url.query)}))
    return JSONResponse({"item": request.path_params["item_id"]})


tools_app = Starlette(routes=[
    Route("/openapi.json", openapi, methods=["GET"]),
    Route("/run_host_command", run_cmd, methods=["POST"]),
    Route("/write_file", write_file, methods=["POST"]),
    Route("/list_tools", list_tools, methods=["GET"]),
    Route("/create_tool", create_tool, methods=["POST"]),
    Route("/items/{item_id}", get_item, methods=["GET"]),
])
