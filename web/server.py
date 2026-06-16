"""ShopSafe web UI — FastAPI server streaming live pipeline runs over SSE.

Run with:  uv run python web/server.py   →   http://localhost:8000
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

# Same bootstrap as agent/main.py: load .env, make `shopsafe` importable, tracing on.
repo_root = Path(__file__).resolve().parent.parent
load_dotenv(repo_root / ".env")
sys.path.insert(0, str(repo_root / "agent"))

from instrumentation import setup_tracing  # noqa: E402

setup_tracing()

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from shopsafe.config import get_config  # noqa: E402
from shopsafe.pipeline import run_pipeline  # noqa: E402

app = FastAPI(title="ShopSafe")

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _sse(event: str, payload: dict) -> str:
    """Format one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.get("/api/stream")
async def stream(q: str):
    """Run the pipeline for query `q`, streaming structured stage events as SSE.

    The pipeline's `on_event` callback fires inside the same event loop, so a
    plain (non-thread-safe) asyncio.Queue is the correct bridge to the response
    generator: callback → queue → SSE frames.
    """
    queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()

    def on_event(kind: str, payload: dict) -> None:
        queue.put_nowait((kind, payload))

    async def generate():
        yield _sse("config", {"describe": get_config().describe()})
        task = asyncio.create_task(run_pipeline(q, on_event=on_event))
        try:
            while True:
                if task.done() and queue.empty():
                    break
                try:
                    kind, payload = await asyncio.wait_for(queue.get(), timeout=0.25)
                except asyncio.TimeoutError:
                    continue
                yield _sse(kind, payload)

            exc = task.exception()
            if exc is not None:
                yield _sse("error", {"message": f"{type(exc).__name__}: {exc}"})
            else:
                yield _sse("final", task.result().model_dump())
            yield _sse("done", {})
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
