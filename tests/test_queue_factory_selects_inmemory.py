"""Test queue factory selection logic."""
import os
import pytest
from app.services.queue import get_queue_backend, InMemoryAsyncQueue, RedisQueueBackend


def test_queue_factory_selects_inmemory():
    """Test that factory selects InMemoryAsyncQueue when no REDIS_URL is set."""
    # Ensure REDIS_URL is not set
    original_redis_url = os.environ.get("REDIS_URL")
    if "REDIS_URL" in os.environ:
        del os.environ["REDIS_URL"]
    
    try:
        # Force recreation of queue backend by clearing global
        import app.services.queue
        app.services.queue._queue_backend = None
        
        # Get backend - should be InMemoryAsyncQueue
        backend = get_queue_backend()
        assert isinstance(backend, InMemoryAsyncQueue), f"Expected InMemoryAsyncQueue, got {type(backend)}"
        
        print("✅ Queue factory selects InMemoryAsyncQueue when no REDIS_URL")
        
    finally:
        # Restore original environment
        if original_redis_url is not None:
            os.environ["REDIS_URL"] = original_redis_url
        
        # Clear global state for other tests
        app.services.queue._queue_backend = None


def test_queue_factory_selects_redis_when_configured():
    """Test that factory selects RedisQueueBackend when REDIS_URL is configured."""
    # Set REDIS_URL environment variable
    original_redis_url = os.environ.get("REDIS_URL")
    os.environ["REDIS_URL"] = "redis://localhost:6379"
    
    try:
        # Force recreation of queue backend by clearing global
        import app.services.queue
        app.services.queue._queue_backend = None
        
        # Get backend - should be RedisQueueBackend
        backend = get_queue_backend()
        assert isinstance(backend, RedisQueueBackend), f"Expected RedisQueueBackend, got {type(backend)}"
        assert backend.redis_url == "redis://localhost:6379"
        
        print("✅ Queue factory selects RedisQueueBackend when REDIS_URL is set")
        
    finally:
        # Restore original environment
        if original_redis_url is not None:
            os.environ["REDIS_URL"] = original_redis_url
        elif "REDIS_URL" in os.environ:
            del os.environ["REDIS_URL"]
        
        # Clear global state for other tests
        app.services.queue._queue_backend = None


async def test_redis_not_configured_graceful():
    """Test that Redis backend gracefully raises NotImplementedError when not configured."""
    redis_backend = RedisQueueBackend("redis://localhost:6379")
    
    # All methods should raise NotImplementedError
    with pytest.raises(NotImplementedError, match="Redis queue backend not implemented"):
        await redis_backend.start()
    
    with pytest.raises(NotImplementedError, match="Redis queue backend not implemented"):
        await redis_backend.stop()
    
    with pytest.raises(NotImplementedError, match="Redis queue backend not implemented"):
        await redis_backend.push(lambda: "test")
    
    print("✅ Redis backend gracefully handles not being configured")


def test_queue_backend_singleton():
    """Test that get_queue_backend returns the same instance."""
    # Clear global state
    import app.services.queue
    app.services.queue._queue_backend = None
    
    # Ensure no REDIS_URL
    original_redis_url = os.environ.get("REDIS_URL")
    if "REDIS_URL" in os.environ:
        del os.environ["REDIS_URL"]
    
    try:
        backend1 = get_queue_backend()
        backend2 = get_queue_backend()
        
        # Should be the same instance
        assert backend1 is backend2, "Queue backend should be singleton"
        assert isinstance(backend1, InMemoryAsyncQueue)
        
        print("✅ Queue backend is singleton")
        
    finally:
        # Restore environment
        if original_redis_url is not None:
            os.environ["REDIS_URL"] = original_redis_url
        
        # Clear global state
        app.services.queue._queue_backend = None


async def test_inmemory_queue_basic_functionality():
    """Test basic InMemoryAsyncQueue functionality."""
    queue = InMemoryAsyncQueue()
    
    # Test starting
    await queue.start()
    assert queue.running == True
    assert queue.queue is not None
    assert queue.worker_task is not None
    
    # Test task execution
    def simple_task(x, y):
        return x + y
    
    future = await queue.push(simple_task, 5, 10)
    result = await future
    assert result == 15
    
    # Test stopping
    await queue.stop()
    assert queue.running == False
    assert queue.queue is None
    assert queue.worker_task is None
    
    print("✅ InMemoryAsyncQueue basic functionality works")


if __name__ == "__main__":
    test_queue_factory_selects_inmemory()
    test_queue_factory_selects_redis_when_configured()
    # test_redis_not_configured_graceful()  # Skip async test in main
    test_queue_backend_singleton()
    # test_inmemory_queue_basic_functionality()  # Skip async test in main