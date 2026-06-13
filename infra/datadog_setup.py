import os
import logging
from ddtrace import tracer, patch_all
from ddtrace.contrib.asyncio import context_provider

logger = logging.getLogger("infra.datadog_setup")

def initialize_datadog():
    """
    Initializes Datadog APM tracing for the agent system.
    Configures distributed tracing, service map identifiers, and patches packages.
    """
    # Check if tracing is enabled via environment variables
    enable_tracing = os.getenv("DD_TRACE_ENABLED", "true").lower() == "true"
    
    if not enable_tracing:
        logger.info("Datadog APM tracing is disabled via DD_TRACE_ENABLED.")
        return False
        
    try:
        # 1. Configure trace context provider for asyncio support
        tracer.configure(context_provider=context_provider)
        
        # 2. Patch standard libraries (asyncio, httpx, redis, sqlalchemy, etc.)
        patch_all(asyncio=True, httpx=True, redis=True, sqlalchemy=True)
        
        # 3. Configure global tags for the service map
        tracer.set_tags({
            "env": os.getenv("DD_ENV", "production"),
            "version": os.getenv("DD_VERSION", "1.0.0"),
            "project": "agent-02-career-assistant",
            "team": "member-5-infra"
        })
        
        logger.info("SUCCESS: Datadog APM auto-instrumentation and distributed tracing initialized.")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Datadog APM: {e}")
        return False

def trace_agent_execution(agent_name: str):
    """
    Decorator to trace agent runner loops inside Datadog APM.
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Start a span for the specific agent in the service map
            with tracer.trace(
                "agent.run",
                service=f"agent-{agent_name.lower().replace('_', '-')}",
                resource=func.__name__
            ) as span:
                span.set_tag("agent.name", agent_name)
                return await func(*args, **kwargs)
        return wrapper
    return decorator

def trace_tool_execution(tool_name: str):
    """
    Decorator to trace tool runs inside Datadog APM.
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            with tracer.trace(
                "agent.tool",
                service="agent-tools-service",
                resource=tool_name
            ) as span:
                span.set_tag("tool.name", tool_name)
                return await func(*args, **kwargs)
        return wrapper
    return decorator
