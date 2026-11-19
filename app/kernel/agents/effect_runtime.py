"""
Effect-like runtime patterns for BEAST.
Port of OpenCode's Effect-based patterns to Python:
- Retry policies with backoff
- Resource management (acquire/release)
- Structured error handling
- Cancellation support
- Observability (spans, metrics)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Awaitable, Callable, Generic, Optional, TypeVar, Union
from functools import wraps
import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")
E = TypeVar("E", bound=Exception)


# =============================================================================
# Effect Types (OpenCode-inspired)
# =============================================================================

class EffectError(Exception):
    """Base class for effect errors."""
    def __init__(self, message: str, cause: Optional[Exception] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.cause = cause
        self.context = context or {}


class TransientError(EffectError):
    """Error that may succeed on retry."""
    pass


class PermanentError(EffectError):
    """Error that will not succeed on retry."""
    pass


class CancellationError(EffectError):
    """Operation was cancelled."""
    pass


class TimeoutError(EffectError):
    """Operation timed out."""
    pass


class ResourceError(EffectError):
    """Resource acquisition/release failed."""
    pass


# =============================================================================
# Retry Policies (OpenCode Effect.retry)
# =============================================================================

@dataclass
class RetryPolicy:
    """Configurable retry policy."""
    max_attempts: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on: tuple[type[Exception], ...] = (TransientError, TimeoutError, ConnectionError)

    def should_retry(self, attempt: int, error: Exception) -> bool:
        if attempt >= self.max_attempts:
            return False
        return isinstance(error, self.retry_on)

    def delay(self, attempt: int) -> float:
        delay = min(self.base_delay * (self.exponential_base ** attempt), self.max_delay)
        if self.jitter:
            import random
            delay *= (0.5 + random.random())  # 0.5-1.5x
        return delay


DEFAULT_RETRY_POLICY = RetryPolicy()
AGGRESSIVE_RETRY_POLICY = RetryPolicy(max_attempts=5, base_delay=0.5, max_delay=60.0)
CONSERVATIVE_RETRY_POLICY = RetryPolicy(max_attempts=2, base_delay=2.0, max_delay=10.0)


async def with_retry(
    operation: Callable[[], Awaitable[T]],
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    on_retry: Optional[Callable[[int, Exception, float], Awaitable[None]]] = None,
) -> T:
    """Execute operation with retry policy (Effect.retry equivalent)."""
    attempt = 0
    last_error = None

    while True:
        try:
            return await operation()
        except Exception as e:
            last_error = e
            if not policy.should_retry(attempt, e):
                logger.error("operation_failed_no_retry", attempt=attempt, error=str(e))
                raise

            delay = policy.delay(attempt)
            logger.warning("operation_retry", attempt=attempt, error=str(e), delay=delay)

            if on_retry:
                await on_retry(attempt, e, delay)

            await asyncio.sleep(delay)
            attempt += 1

    # Unreachable, but satisfies type checker
    raise last_error


# =============================================================================
# Timeout (OpenCode Effect.timeout)
# =============================================================================

async def with_timeout(
    operation: Callable[[], Awaitable[T]],
    timeout_seconds: float,
    on_timeout: Optional[Callable[[], Awaitable[None]]] = None,
) -> T:
    """Execute operation with timeout (Effect.timeout equivalent)."""
    try:
        return await asyncio.wait_for(operation(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        if on_timeout:
            await on_timeout()
        raise TimeoutError(f"Operation timed out after {timeout_seconds}s")


# =============================================================================
# Resource Management (OpenCode Effect.acquireRelease)
# =============================================================================

@dataclass
class Resource(Generic[T]):
    """Managed resource with acquire/release."""
    acquire: Callable[[], Awaitable[T]]
    release: Callable[[T], Awaitable[None]]
    name: str = "resource"

    async def __aenter__(self) -> T:
        self.value = await self.acquire()
        logger.debug("resource_acquired", resource=self.name)
        return self.value

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if hasattr(self, "value"):
            try:
                await self.release(self.value)
                logger.debug("resource_released", resource=self.name)
            except Exception as e:
                logger.error("resource_release_failed", resource=self.name, error=str(e))
                raise ResourceError(f"Failed to release {self.name}", cause=e)


@asynccontextmanager
async def managed_resource(
    acquire: Callable[[], Awaitable[T]],
    release: Callable[[T], Awaitable[None]],
    name: str = "resource",
) -> AsyncGenerator[T, None]:
    """Context manager for managed resources (Effect.acquireRelease equivalent)."""
    resource = await acquire()
    logger.debug("resource_acquired", resource=name)
    try:
        yield resource
    finally:
        try:
            await release(resource)
            logger.debug("resource_released", resource=name)
        except Exception as e:
            logger.error("resource_release_failed", resource=name, error=str(e))
            raise ResourceError(f"Failed to release {name}", cause=e)


# =============================================================================
# Cancellation (OpenCode Effect.interruptible)
# =============================================================================

class CancellationToken:
    """Token for cooperative cancellation."""
    def __init__(self):
        self._cancelled = False
        self._callbacks: list[Callable[[], None]] = []

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True
        for cb in self._callbacks:
            try:
                cb()
            except Exception:
                pass  # Ignore callback errors

    def register(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register cancellation callback, returns unregister function."""
        self._callbacks.append(callback)
        return lambda: self._callbacks.remove(callback) if callback in self._callbacks else None

    def throw_if_cancelled(self) -> None:
        if self._cancelled:
            raise CancellationError("Operation cancelled")


async def with_cancellation(
    operation: Callable[[CancellationToken], Awaitable[T]],
    token: Optional[CancellationToken] = None,
) -> T:
    """Execute operation with cancellation support."""
    token = token or CancellationToken()
    return await operation(token)


# =============================================================================
# Observability / Spans (OpenCode Effect.withLogSpan)
# =============================================================================

@dataclass
class Span:
    """Observability span (OpenCode Effect.span equivalent)."""
    name: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    parent: Optional["Span"] = None
    children: list["Span"] = field(default_factory=list)

    def end(self, attributes: Optional[Dict[str, Any]] = None) -> None:
        self.end_time = time.time()
        if attributes:
            self.attributes.update(attributes)
        logger.info(
            "span_end",
            span=self.name,
            duration_ms=(self.end_time - self.start_time) * 1000,
            attributes=self.attributes,
        )

    def add_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def child(self, name: str) -> "Span":
        child = Span(name=name, parent=self)
        self.children.append(child)
        return child


class SpanContext:
    """Manages current span context."""
    def __init__(self):
        self._current: Optional[Span] = None

    @property
    def current(self) -> Optional[Span]:
        return self._current

    @asynccontextmanager
    async def span(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> AsyncGenerator[Span, None]:
        parent = self._current
        span = Span(name=name, parent=parent)
        if attributes:
            span.attributes.update(attributes)

        if parent:
            parent.children.append(span)

        self._current = span
        logger.debug("span_start", span=name, attributes=attributes or {})

        try:
            yield span
        except Exception as e:
            span.add_attribute("error", str(e))
            span.add_attribute("error_type", type(e).__name__)
            raise
        finally:
            span.end()
            self._current = parent


# Global span context
_span_context = SpanContext()


def get_span_context() -> SpanContext:
    return _span_context


@asynccontextmanager
async def span(name: str, attributes: Optional[Dict[str, Any]] = None) -> AsyncGenerator[Span, None]:
    """Create a span (Effect.withLogSpan equivalent)."""
    async with _span_context.span(name, attributes) as s:
        yield s


# =============================================================================
# Structured Errors (OpenCode Effect.cause)
# =============================================================================

def with_cause(error: Exception, cause: Exception, context: Optional[Dict[str, Any]] = None) -> EffectError:
    """Wrap error with cause (Effect.cause equivalent)."""
    return EffectError(
        message=str(error),
        cause=cause,
        context=context or {}
    )


def as_transient(error: Exception, context: Optional[Dict[str, Any]] = None) -> TransientError:
    """Mark error as transient (retryable)."""
    if isinstance(error, TransientError):
        if context:
            error.context.update(context)
        return error
    return TransientError(str(error), cause=error, context=context)


def as_permanent(error: Exception, context: Optional[Dict[str, Any]] = None) -> PermanentError:
    """Mark error as permanent (non-retryable)."""
    if isinstance(error, PermanentError):
        if context:
            error.context.update(context)
        return error
    return PermanentError(str(error), cause=error, context=context)


# =============================================================================
# Effect Combinators (OpenCode Effect.zip, Effect.all, etc.)
# =============================================================================

async def zip_effects(*operations: Callable[[], Awaitable[Any]]) -> list[Any]:
    """Run effects in parallel, return results in order (Effect.zip equivalent)."""
    return await asyncio.gather(*[op() for op in operations])


async def all_effects(*operations: Callable[[], Awaitable[Any]]) -> list[Any]:
    """Run all effects in parallel, fail fast on first error (Effect.all equivalent)."""
    return await asyncio.gather(*[op() for op in operations])


async def race_effects(*operations: Callable[[], Awaitable[Any]]) -> Any:
    """Return first completed result (Effect.race equivalent)."""
    return await asyncio.wait(
        [asyncio.create_task(op()) for op in operations],
        return_when=asyncio.FIRST_COMPLETED
    )


# =============================================================================
# Tool Execution Effect (OpenCode AgentToolRuntime pattern)
# =============================================================================

@dataclass
class ToolExecution:
    """Tool execution with full effect runtime support."""
    tool_id: str
    arguments: Dict[str, Any]
    execution_target: str = "local"
    approval_id: Optional[str] = None
    timeout_seconds: float = 30.0
    retry_policy: RetryPolicy = field(default_factory=lambda: DEFAULT_RETRY_POLICY)

    async def execute(
        self,
        executor: Callable[[str, Dict[str, Any], str, Optional[str]], Awaitable[Dict[str, Any]]],
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        """Execute tool with full effect runtime."""
        async with span(f"tool.{self.tool_id}", {
            "tool_id": self.tool_id,
            "execution_target": self.execution_target,
            "timeout_seconds": self.timeout_seconds,
        }) as s:
            start_time = time.time()

            try:
                # Execute with timeout and retry
                result = await with_timeout(
                    lambda: with_retry(
                        lambda: executor(
                            self.tool_id,
                            self.arguments,
                            self.execution_target,
                            self.approval_id,
                        ),
                        policy=self.retry_policy,
                    ),
                    timeout_seconds=self.timeout_seconds,
                )

                duration_ms = int((time.time() - start_time) * 1000)
                s.add_attribute("duration_ms", duration_ms)
                s.add_attribute("status", "success")

                logger.info(
                    "tool_executed",
                    tool_id=self.tool_id,
                    duration_ms=duration_ms,
                    target=self.execution_target,
                )

                return result

            except TimeoutError as e:
                duration_ms = int((time.time() - start_time) * 1000)
                s.add_attribute("duration_ms", duration_ms)
                s.add_attribute("status", "timeout")
                raise

            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                s.add_attribute("duration_ms", duration_ms)
                s.add_attribute("status", "error")
                s.add_attribute("error", str(e))
                raise


# =============================================================================
# Decorators for Effect-style functions
# =============================================================================

def effect(
    retry_policy: Optional[RetryPolicy] = None,
    timeout_seconds: Optional[float] = None,
    span_name: Optional[str] = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator to add effect runtime to async function."""
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            effective_span = span_name or f"{func.__module__}.{func.__name__}"
            async with span(effective_span) as s:
                try:
                    if timeout_seconds:
                        return await with_timeout(func, timeout_seconds, *args, **kwargs)
                    elif retry_policy:
                        return await with_retry(lambda: func(*args, **kwargs), retry_policy)
                    else:
                        return await func(*args, **kwargs)
                except Exception as e:
                    s.add_attribute("error", str(e))
                    s.add_attribute("error_type", type(e).__name__)
                    raise
        return wrapper
    return decorator


# =============================================================================
# Metrics Collection (OpenCode Effect metrics)
# =============================================================================

@dataclass
class EffectMetrics:
    """Collected metrics for an effect."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_duration_ms: float = 0.0
    errors: Dict[str, int] = field(default_factory=dict)

    def record_success(self, duration_ms: float) -> None:
        self.total_calls += 1
        self.successful_calls += 1
        self.total_duration_ms += duration_ms

    def record_failure(self, error: Exception, duration_ms: float) -> None:
        self.total_calls += 1
        self.failed_calls += 1
        self.total_duration_ms += duration_ms
        error_type = type(error).__name__
        self.errors[error_type] = self.errors.get(error_type, 0) + 1

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.successful_calls / self.total_calls

    @property
    def avg_duration_ms(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_duration_ms / self.total_calls


# Global metrics registry
_metrics_registry: Dict[str, EffectMetrics] = {}


def get_metrics(name: str) -> EffectMetrics:
    if name not in _metrics_registry:
        _metrics_registry[name] = EffectMetrics()
    return _metrics_registry[name]


def record_metrics(name: str, success: bool, duration_ms: float, error: Optional[Exception] = None) -> None:
    metrics = get_metrics(name)
    if success:
        metrics.record_success(duration_ms)
    else:
        metrics.record_failure(error, duration_ms)


def with_metrics(name: str) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator to automatically record metrics."""
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                record_metrics(name, True, (time.time() - start) * 1000)
                return result
            except Exception as e:
                record_metrics(name, False, (time.time() - start) * 1000, e)
                raise
        return wrapper
    return decorator


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    async def example():
        # Example 1: Retry with custom policy
        policy = RetryPolicy(max_attempts=3, base_delay=0.5, max_delay=5.0)

        @with_metrics("example.operation")
        @effect(retry_policy=policy, timeout_seconds=10.0, span_name="example.operation")
        async def unreliable_operation(x: int) -> str:
            import random
            if random.random() < 0.7:
                raise TransientError("Random failure")
            return f"Success: {x}"

        # Example 2: Resource management
        async def acquire_db() -> str:
            await asyncio.sleep(0.1)
            return "db_connection_123"

        async def release_db(conn: str) -> None:
            await asyncio.sleep(0.05)

        async with managed_resource(acquire_db, release_db, "database") as conn:
            print(f"Using {conn}")

        # Example 3: Cancellation
        token = CancellationToken()

        async def long_operation(token: CancellationToken) -> str:
            for i in range(100):
                token.throw_if_cancelled()
                await asyncio.sleep(0.1)
            return "done"

        # Example 4: Parallel effects
        async def op1() -> str:
            await asyncio.sleep(0.5)
            return "result1"

        async def op2() -> str:
            await asyncio.sleep(0.3)
            return "result2"

        results = await zip_effects(op1, op2)
        print(f"Parallel results: {results}")

        # Example 5: Span context
        async with span("parent_operation") as parent:
            parent.add_attribute("user_id", "123")
            async with span("child_operation") as child:
                child.add_attribute("item_id", "456")
                await asyncio.sleep(0.1)

    asyncio.run(example())