"""
Real-time log streaming infrastructure.

Captures every record from the 'career_assistant' logger tree (plus uvicorn),
keeps a rolling in-memory history, and fans new records out to any connected
SSE clients.
"""
import asyncio
import logging
import os
from collections import deque
from datetime import datetime
from typing import Deque, List, Optional

HISTORY_SIZE = 2000          # how many past lines to keep for "what has happened"
LOGGERS_TO_CAPTURE = ["career_assistant", "uvicorn.error", "uvicorn.access"]

class LogBroadcaster:
    """Holds history + the set of live subscriber queues."""
    def __init__(self, history_size: int = HISTORY_SIZE):
        self.history: Deque[dict] = deque(maxlen=history_size)
        self.subscribers: List[asyncio.Queue] = []
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._seq = 0

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    def publish(self, entry: dict):
        self._seq += 1
        entry["id"] = self._seq
        self.history.append(entry)

        for q in list(self.subscribers):
            try:
                if self.loop and self.loop.is_running():
                    # safe whether called from the loop thread or a worker thread
                    self.loop.call_soon_threadsafe(q.put_nowait, entry)
                else:
                    q.put_nowait(entry)
            except Exception:
                pass

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self.subscribers:
            self.subscribers.remove(q)

broadcaster = LogBroadcaster()

class BroadcastHandler(logging.Handler):
    """A logging handler that pushes formatted records into the broadcaster."""
    def emit(self, record: logging.LogRecord):
        try:
            entry = {
                "time": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                "ts": record.created,
                "level": record.levelname,
                "logger": record.name,
                # format() appends the traceback automatically when exc_info is set
                "message": self.format(record),
            }
            broadcaster.publish(entry)
        except Exception:
            self.handleError(record)

def setup_logging(loop: Optional[asyncio.AbstractEventLoop] = None,
                  level: int = logging.INFO) -> LogBroadcaster:
    """Attach the broadcast handler. Call once on app startup."""
    if loop is not None:
        broadcaster.set_loop(loop)
        
    os.makedirs("logs", exist_ok=True)
    file_handler = logging.FileHandler("logs/app.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    handler = BroadcastHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))

    for name in LOGGERS_TO_CAPTURE:
        lg = logging.getLogger(name)
        lg.setLevel(level)
        if not any(isinstance(h, logging.FileHandler) for h in lg.handlers):
            lg.addHandler(file_handler)
        if not any(isinstance(h, BroadcastHandler) for h in lg.handlers):
            lg.addHandler(handler)

    return broadcaster
