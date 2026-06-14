"""
Scraping queue manager utilizing asyncio.Queue for rate limiting and retry scheduling.
"""

import asyncio
import logging
import random
from typing import Callable, Coroutine, Any, Dict, List
from config import settings

logger = logging.getLogger("career_assistant.scraping_queue")

class ScrapingTask:
    """Represents a queued scraping task."""
    def __init__(self, func: Callable[..., Coroutine[Any, Any, Any]], args: tuple, kwargs: dict, max_retries: int = 3):
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.retries = 0
        self.max_retries = max_retries
        self.backoff = getattr(settings, "RETRY_BASE_DELAY", 1.0)

class ScrapingQueue:
    """Bounded queue scheduler with worker processing and exponential backoff retry scheduling."""
    def __init__(self, queue_size: int = None, num_workers: int = 1):
        if queue_size is None:
            queue_size = getattr(settings, "RATE_LIMIT_QUEUE_SIZE", 100)
        self.queue = asyncio.Queue(maxsize=queue_size)
        self.num_workers = num_workers
        self.workers: List[asyncio.Task] = []
        self.results: List[Any] = []
        self.is_running = False

    async def start(self):
        """Start worker loop tasks."""
        self.is_running = True
        self.workers = [asyncio.create_task(self._worker(i)) for i in range(self.num_workers)]
        logger.info(f"ScrapingQueue started with {self.num_workers} workers.")

    async def stop(self):
        """Stop worker tasks and join the queue."""
        self.is_running = False
        # Feed None values to signal workers to shut down (non-blocking if full)
        for _ in range(self.num_workers):
            try:
                self.queue.put_nowait(None)
            except asyncio.QueueFull:
                pass
        await asyncio.gather(*self.workers, return_exceptions=True)
        logger.info("ScrapingQueue workers stopped.")

    async def add_task(self, func: Callable[..., Coroutine[Any, Any, Any]], *args, max_retries: int = 3, **kwargs):
        """Add a task to the bounded queue."""
        task = ScrapingTask(func, args, kwargs, max_retries=max_retries)
        await self.queue.put(task)
        logger.info(f"Task added to scraping queue. Queue depth: {self.queue.qsize()}")

    async def _worker(self, worker_id: int):
        """Worker task processing loop."""
        while self.is_running:
            task = await self.queue.get()
            if task is None:
                self.queue.task_done()
                break

            try:
                logger.info(f"Worker {worker_id} processing task (attempt {task.retries + 1}/{task.max_retries + 1}).")
                # Apply politeness rate limiting before fetching
                min_delay = getattr(settings, "MIN_DELAY", 2.0)
                max_delay = getattr(settings, "MAX_DELAY", 4.0)
                delay = random.uniform(min_delay, max_delay)
                logger.info(f"Worker {worker_id} rate-limiting: sleeping {delay:.1f}s")
                await asyncio.sleep(delay)

                result = await task.func(*task.args, **task.kwargs)
                self.results.append(result)
                logger.info(f"Worker {worker_id} completed task successfully.")
            except Exception as exc:
                logger.warning(f"Worker {worker_id} failed task on attempt {task.retries + 1}: {exc}")
                if task.retries < task.max_retries:
                    task.retries += 1
                    factor = getattr(settings, "RETRY_BACKOFF_FACTOR", 2.0)
                    max_d = getattr(settings, "RETRY_MAX_DELAY", 60.0)
                    task.backoff = min(max_d, task.backoff * factor)
                    # Reschedule retry as a task to not block this worker
                    asyncio.create_task(self._requeue_with_delay(task))
                else:
                    logger.error(f"Task exceeded max retries. Dropping task. Error: {exc}")
            finally:
                self.queue.task_done()

    async def _requeue_with_delay(self, task: ScrapingTask):
        """Wait for backoff delay then requeue task."""
        logger.info(f"Re-scheduling task retry in {task.backoff:.1f}s (exponential backoff)")
        await asyncio.sleep(task.backoff)
        try:
            await self.queue.put(task)
            logger.info("Task successfully re-inserted into the queue.")
        except Exception as e:
            logger.error(f"Failed to requeue task: {e}")
