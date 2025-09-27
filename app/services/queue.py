import os
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional
from concurrent.futures import Future

logger = logging.getLogger(__name__)


class QueueBackend(ABC):
    """Abstract interface for task queue backends."""
    
    @abstractmethod
    async def push(self, task_callable: Callable, *args, **kwargs) -> Future:
        """Push a task to the queue."""
        pass
    
    @abstractmethod
    async def start(self):
        """Start the queue worker."""
        pass
    
    @abstractmethod
    async def stop(self):
        """Stop the queue worker."""
        pass


class RedisQueueBackend(QueueBackend):
    """Redis-based queue backend implementation."""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis_client = None
        self.running = False
        
    async def push(self, task_callable: Callable, *args, **kwargs) -> Future:
        """Push a task to Redis queue."""
        raise NotImplementedError("Redis queue backend not implemented - requires redis dependency")
    
    async def start(self):
        """Start the Redis queue."""
        raise NotImplementedError("Redis queue backend not implemented - requires redis dependency")
    
    async def stop(self):
        """Stop the Redis queue."""
        raise NotImplementedError("Redis queue backend not implemented - requires redis dependency")


class InMemoryAsyncQueue(QueueBackend):
    """In-memory async queue implementation using asyncio.Queue."""
    
    def __init__(self):
        self.queue: Optional[asyncio.Queue] = None
        self.worker_task: Optional[asyncio.Task] = None
        self.running = False
        
    async def push(self, task_callable: Callable, *args, **kwargs) -> Future:
        """Push a task to the queue and return a Future for the result."""
        if not self.running or not self.queue:
            raise RuntimeError("Queue not started")
            
        future = asyncio.get_event_loop().create_future()
        task_item = {
            "callable": task_callable,
            "args": args,
            "kwargs": kwargs,
            "future": future
        }
        
        await self.queue.put(task_item)
        logger.debug(f"Task queued: {task_callable.__name__}")
        return future
    
    async def start(self):
        """Start the queue and worker task."""
        if self.running:
            return
            
        self.queue = asyncio.Queue()
        self.running = True
        self.worker_task = asyncio.create_task(self._worker())
        logger.info("InMemoryAsyncQueue started")
    
    async def stop(self):
        """Stop the queue and worker task."""
        if not self.running:
            return
            
        self.running = False
        
        if self.worker_task and not self.worker_task.done():
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        
        self.worker_task = None
        self.queue = None
        logger.info("InMemoryAsyncQueue stopped")
    
    async def _worker(self):
        """Worker coroutine that processes tasks sequentially."""
        logger.info("Queue worker started")
        
        while self.running:
            try:
                # Wait for a task with timeout
                task_item = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                
                try:
                    # Execute the task
                    callable_func = task_item["callable"]
                    args = task_item["args"]
                    kwargs = task_item["kwargs"]
                    future = task_item["future"]
                    
                    logger.debug(f"Executing task: {callable_func.__name__}")
                    
                    # Handle both sync and async callables
                    if asyncio.iscoroutinefunction(callable_func):
                        result = await callable_func(*args, **kwargs)
                    else:
                        result = callable_func(*args, **kwargs)
                    
                    future.set_result(result)
                    logger.debug(f"Task completed: {callable_func.__name__}")
                    
                except Exception as e:
                    logger.error(f"Task execution failed: {e}")
                    task_item["future"].set_exception(e)
                
                finally:
                    self.queue.task_done()
                    
            except asyncio.TimeoutError:
                # Continue the loop, allows clean shutdown
                continue
            except asyncio.CancelledError:
                logger.info("Queue worker cancelled")
                break
            except Exception as e:
                logger.error(f"Queue worker error: {e}")


# Global queue instance
_queue_backend: Optional[QueueBackend] = None


def get_queue_backend() -> QueueBackend:
    """Get the global queue backend instance."""
    global _queue_backend
    if _queue_backend is None:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            _queue_backend = RedisQueueBackend(redis_url)
        else:
            _queue_backend = InMemoryAsyncQueue()
    return _queue_backend


def is_queue_enabled() -> bool:
    """Check if queue processing is enabled via environment variable."""
    return os.getenv("USE_QUEUE", "false").lower() == "true"


async def execute_with_queue(task_callable: Callable, *args, **kwargs):
    """Execute a task either directly or via queue depending on USE_QUEUE flag."""
    if is_queue_enabled():
        queue = get_queue_backend()
        if not queue.running:
            await queue.start()
        
        future = await queue.push(task_callable, *args, **kwargs)
        return await future
    else:
        # Direct execution
        if asyncio.iscoroutinefunction(task_callable):
            return await task_callable(*args, **kwargs)
        else:
            return task_callable(*args, **kwargs)