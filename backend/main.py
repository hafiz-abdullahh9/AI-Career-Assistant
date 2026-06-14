import sys
import asyncio

# Playwright/crawl4ai launches a browser subprocess. On Windows the default
# Selector event loop can't spawn subprocesses and raises a bare
# NotImplementedError, so force the subprocess-capable Proactor loop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import os
import io

# Force UTF-8 encoding for Windows console to prevent Crawl4AI crashing on special characters
if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import uvicorn
import asyncio
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

from agents.job_scraping_agent import JobScrapingAgent
from agents.job_verification_agent import JobVerificationAgent
from backend.log_stream import broadcaster, setup_logging

app = FastAPI(title="Job Scraper & Verification API")

@app.on_event("startup")
async def _init_log_stream():
    setup_logging(loop=asyncio.get_running_loop())
    import logging
    logging.getLogger("career_assistant").info(
        f"Event loop in use: {type(asyncio.get_running_loop()).__name__}"
    )


# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScrapeRequest(BaseModel):
    keyword: str
    location: str = ""
    job_type: str = ""
    experience_level: str = ""
    platforms: List[str] = ["indeed", "linkedin"]
    max_pages: int = 1

class VerifyRequest(BaseModel):
    jobs: List[dict]

active_scrape_task: Optional[asyncio.Task] = None

@app.post("/api/scrape")
async def api_scrape(req: ScrapeRequest):
    global active_scrape_task
    if active_scrape_task is not None and not active_scrape_task.done():
        raise HTTPException(status_code=400, detail="A scrape is already in progress.")

    agent = JobScrapingAgent()
    active_scrape_task = asyncio.create_task(
        agent.scrape_jobs(
            keyword=req.keyword,
            location=req.location,
            job_type=req.job_type,
            experience_level=req.experience_level,
            platforms=req.platforms,
            max_pages=req.max_pages
        )
    )

    try:
        result = await active_scrape_task
        return result
    except asyncio.CancelledError:
        return {"status": "cancelled", "jobs": [], "total_found": 0, "errors": ["Scrape was cancelled by user"]}
    finally:
        active_scrape_task = None

@app.post("/api/scrape/cancel")
async def api_scrape_cancel():
    global active_scrape_task
    if active_scrape_task is not None and not active_scrape_task.done():
        active_scrape_task.cancel()
        return {"status": "cancelling"}
    return {"status": "not running"}


@app.post("/api/verify")
async def api_verify(req: VerifyRequest):
    agent = JobVerificationAgent()
    # verify_jobs is synchronous but does a lot of work
    verified_jobs = agent.verify_jobs(req.jobs)
    return {"jobs": verified_jobs}

def _sse(entry: dict) -> str:
    # the `id:` line lets the browser resume without re-sending old lines
    return f"id: {entry['id']}\ndata: {json.dumps(entry)}\n\n"

@app.get("/api/logs")
async def get_logs():
    """Full history snapshot (everything that has happened)."""
    return JSONResponse(list(broadcaster.history))

@app.get("/api/logs/stream")
async def stream_logs(request: Request):
    """Live SSE stream: replays history, then streams new lines forever."""
    # Resume support: on reconnect the browser sends the last id it saw.
    try:
        last_id = int(request.headers.get("last-event-id") or 0)
    except ValueError:
        last_id = 0

    async def event_gen():
        q = broadcaster.subscribe()
        try:
            # 1) replay everything that has happened (only newer than last_id)
            for entry in list(broadcaster.history):
                if entry["id"] > last_id:
                    yield _sse(entry)
            # 2) then stream live
            while True:
                if await request.is_disconnected():
                    break
                try:
                    entry = await asyncio.wait_for(q.get(), timeout=15)
                    yield _sse(entry)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"   # comment line keeps the connection open
        finally:
            broadcaster.unsubscribe(q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Mount frontend directory
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
else:
    print(f"Warning: Frontend directory not found at {frontend_dir}")

if __name__ == "__main__":
    import sys
    import asyncio
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    # reload=True spawns a child process that resets the Windows event loop
    # back to the Selector loop (which can't launch the Playwright subprocess),
    # so keep reload off while scraping.
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
