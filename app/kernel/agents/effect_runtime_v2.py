"""
Effect-like Runtime for BEAST - Enhanced v2.
More closely mirrors Effect TS API patterns:
- Effect<A, E, R> type with success, error, requirements
- Effect.gen for generator-based effects
- Layer pattern for dependency injection
- Scope for resource lifecycle
- Fiber for concurrent execution
- Supervisor for fiber management
"""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import (
    Any, AsyncGenerator, Awaitable, Callable, Dict, Generic, List, Optional,
    TypeVar, Union, Coroutine, Protocol, runtime_checkable
)
from functools import wraps
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)

# Type variables
A = TypeVar("A")  # Success type
E = TypeVar("E", bound=BaseException)  # Error type
R = TypeVar("R")  # Requirements/Context type

# =============================================================================
# Effect Types (OpenCode-inspired, mirrors Effect TS)
# =============================================================================

class EffectError(Exception):
    """Base class for effect errors with cause chain."""
    def __init__(self, message: str, cause: Optional[Exception] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.cause = cause
        self.context = context or {}
        self._tag = "EffectError"

    def tag(self, tag: str) -> "EffectError":
        self._tag = tag
        return self

    def annotate(self, **kwargs) -> "EffectError":
        self.context.update(kwargs)
        return self


class TransientError(EffectError):
    """Error that may succeed on retry."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tag = "TransientError"


class PermanentError(EffectError):
    """Error that will not succeed on retry."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tag = "PermanentError"


class CancellationError(EffectError):
    """Operation was cancelled."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tag = "CancellationError"


class TimeoutError(EffectError):
    """Operation timed out."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tag = "TimeoutError"


class ResourceError(EffectError):
    """Resource acquisition/release failed."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tag = "ResourceError"


# =============================================================================
# Effect<T, E, R> - Core Effect Type (mirrors Effect TS)
# =============================================================================

class Effect(Generic[A, E, R]):
    """
    Core Effect type: Effect<Success, Error, Requirements>
    
    Mirrors Effect TS: Effect<A, E, R>
    - A: Success type
    - E: Error type  
    - R: Requirements (environment/dependencies)
    """
    
    def __init__(self, operation: Callable[[], Awaitable[A]]):
        self._operation = operation
        self._error_handler: Optional[Callable[[E], Awaitable[A]]] = None
        self._finally_handlers: List[Callable[[], Awaitable[None]]] = []
        self._requirements: Dict[str, Any] = {}
        self._span_name: Optional[str] = None
        self._retry_policy: Optional["RetryPolicy"] = None
        self._timeout_seconds: Optional[float] = None
        self._cancellation_token: Optional["CancellationToken"] = None
    
    # ----- Combinators (Effect.map, Effect.flatMap, Effect.zip) -----
    
    def map(self, f: Callable[[A], Union[A, Awaitable[A]]]) -> "Effect[A, E, R]":
        """Transform success value (Effect.map)."""
        async def mapped():
            result = await self._run()
            transformed = f(result)
            if asyncio.iscoroutine(transformed):
                return await transformed
            return transformed
        return Effect(mapped)._inherit_config(self)
    
    def flat_map(self, f: Callable[[A], "Effect[A, E, R]"]) -> "Effect[A, E, R]":
        """Chain effects (Effect.flatMap / Effect.bind)."""
        async def chained():
            result = await self._run()
            next_effect = f(result)
            return await next_effect._run()
        return Effect(chained)._inherit_config(self)
    
    def zip(self, other: "Effect[Any, E, R]") -> "Effect[tuple, E, R]":
        """Run effects in parallel, return tuple (Effect.zip)."""
        async def zipped():
            return await asyncio.gather(self._run(), other._run())
        return Effect(zipped)._inherit_config(self)
    
    def zip_with(self, other: "Effect[Any, E, R]", f: Callable[[A, Any], Awaitable[A]]) -> "Effect[A, E, R]":
        """Run effects in parallel, combine with function."""
        async def zipped():
            a, b = await asyncio.gather(self._run(), other._run())
            return await f(a, b)
        return Effect(zipped)._inherit_config(self)
    
    def fork(self) -> "Fiber[A, E]":
        """Start effect in background (Effect.fork)."""
        return Fiber(asyncio.create_task(self._run()))
    
    def race(self, other: "Effect[A, E, R]") -> "Effect[A, E, R]":
        """Return first completed result (Effect.race)."""
        async def raced():
            done, pending = await asyncio.wait(
                [asyncio.create_task(self._run()), asyncio.create_task(other._run())],
                return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            return done.pop().result()
        return Effect(raced)._inherit_config(self)
    
    def timeout(self, seconds: float) -> "Effect[A, E, R]":
        """Add timeout (Effect.timeout)."""
        self._timeout_seconds = seconds
        return self
    
    def retry(self, policy: Optional["RetryPolicy"] = None) -> "Effect[A, E, R]":
        """Add retry policy (Effect.retry)."""
        self._retry_policy = policy or DEFAULT_RETRY_POLICY
        return self
    
    def catch_all(self, handler: Callable[[E], Awaitable[A]]) -> "Effect[A, Never, R]":
        """Handle all errors (Effect.catchAll)."""
        self._error_handler = handler
        return self  # type: ignore
    
    def catch_tag(self, tag: str, handler: Callable[[EffectError], Awaitable[A]]) -> "Effect[A, E, R]":
        """Handle specific error tag (Effect.catchTag)."""
        async def wrapped_handler(e: E):
            if isinstance(e, EffectError) and e._tag == tag:
                return await handler(e)
            raise e
        self._error_handler = wrapped_handler  # type: ignore
        return self
    
    def ensuring(self, finalizer: Callable[[], Awaitable[None]]) -> "Effect[A, E, R]":
        """Run finalizer on success or failure (Effect.ensuring)."""
        self._finally_handlers.append(finalizer)
        return self
    
    def provide(self, **requirements) -> "Effect[A, E, R]":
        """Provide requirements (Effect.provideService)."""
        self._requirements.update(requirements)
        return self
    
    def with_span(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> "Effect[A, E, R]":
        """Add observability span (Effect.withLogSpan)."""
        self._span_name = name
        if attributes:
            self._span_attributes = attributes
        return self
    
    def with_cancellation(self, token: Optional["CancellationToken"] = None) -> "Effect[A, E, R]":
        """Add cancellation support."""
        self._cancellation_token = token
        return self
    
    def _inherit_config(self, other: "Effect") -> "Effect":
        """Inherit configuration from another effect."""
        self._error_handler = other._error_handler
        self._finally_handlers = other._finally_handlers.copy()
        self._requirements = other._requirements.copy()
        self._span_name = other._span_name
        self._retry_policy = other._retry_policy
        self._timeout_seconds = other._timeout_seconds
        self._cancellation_token = other._cancellation_token
        return self
    
    async def _run(self) -> A:
        """Execute the effect with all configured behaviors."""
        operation = self._operation
        
        # Apply retry policy
        if self._retry_policy:
            operation = self._wrap_with_retry(operation)
        
        # Apply timeout
        if self._timeout_seconds:
            operation = self._wrap_with_timeout(operation)
        
        # Apply cancellation
        if self._cancellation_token:
            operation = self._wrap_with_cancellation(operation)
        
        # Apply span
        if self._span_name:
            operation = self._wrap_with_span(operation)
        
        # Execute with error handling and finalizers
        try:
            result = await operation()
            return result
        except Exception as e:
            if self._error_handler:
                return await self._error_handler(e)  # type: ignore
            raise
        finally:
            for handler in self._finally_handlers:
                try:
                    await handler()
                except Exception:
                    pass  # Ignore finalizer errors
    
    def _wrap_with_retry(self, operation: Callable[[], Awaitable[A]]) -> Callable[[], Awaitable[A]]:
        async def with_retry():
            attempt = 0
            while True:
                try:
                    return await operation()
                except Exception as e:
                    if not self._retry_policy.should_retry(attempt, e):
                        raise
                    delay = self._retry_policy.delay(attempt)
                    logger.warning("effect_retry", attempt=attempt, error=str(e), delay=delay)
                    await asyncio.sleep(delay)
                    attempt += 1
        return with_retry
    
    def _wrap_with_timeout(self, operation: Callable[[], Awaitable[A]]) -> Callable[[], Awaitable[A]]:
        async def with_timeout():
            try:
                return await asyncio.wait_for(operation(), timeout=self._timeout_seconds)
            except asyncio.TimeoutError:
                raise TimeoutError(f"Operation timed out after {self._timeout_seconds}s")
        return with_timeout
    
    def _wrap_with_cancellation(self, operation: Callable[[], Awaitable[A]]) -> Callable[[], Awaitable[A]]:
        async def with_cancellation():
            if self._cancellation_token:
                self._cancellation_token.throw_if_cancelled()
            return await operation()
        return with_cancellation
    
    def _wrap_with_span(self, operation: Callable[[], Awaitable[A]]) -> Callable[[], Awaitable[A]]:
        async def with_span():
            async with span(self._span_name, getattr(self, '_span_attributes', None)) as s:
                return await operation()
        return with_span
    
    # ----- Runner methods -----
    
    async def run(self) -> A:
        """Run effect and return result."""
        return await self._run()
    
    def run_sync(self) -> A:
        """Run effect synchronously (for testing)."""
        return asyncio.run(self._run())


# Type for "never" error (all errors handled)
class Never:
    pass


# =============================================================================
# Effect Constructors (Effect.succeed, Effect.fail, Effect.async, etc.)
# =============================================================================

def succeed[A](value: A) -> Effect[A, Never, Any]:
    """Create effect that succeeds with value (Effect.succeed)."""
    return Effect(lambda: value)


def fail[E](error: E) -> Effect[Never, E, Any]:
    """Create effect that fails with error (Effect.fail)."""
    async def fail_op():
        raise error
    return Effect(fail_op)


def async_effect[A, E](operation: Callable[[], Awaitable[A]]) -> Effect[A, E, Any]:
    """Create effect from async operation (Effect.async)."""
    return Effect(operation)


def sync_effect[A, E](operation: Callable[[], A]) -> Effect[A, E, Any]:
    """Create effect from sync operation (Effect.sync)."""
    async def op():
        return operation()
    return Effect(op)


def try_effect[A, E](operation: Callable[[], A]) -> Effect[A, E, Any]:
    """Create effect from sync operation that might throw (Effect.try)."""
    async def op():
        return operation()
    return Effect(op)


async def with_timeout(
    operation: Callable[[], Awaitable[A]],
    timeout_seconds: float,
    on_timeout: Optional[Callable[[], Awaitable[None]]] = None,
) -> A:
    """Execute operation with timeout (Effect.timeout equivalent)."""
    try:
        return await asyncio.wait_for(operation(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        if on_timeout:
            await on_timeout()
        raise TimeoutError(f"Operation timed out after {timeout_seconds}s")


def suspend[A, E, R](effect: Callable[[], Effect[A, E, R]]) -> Effect[A, E, R]:
    """Defer effect creation (Effect.suspend)."""
    return Effect(lambda: effect()._run())


# =============================================================================
# Effect.gen - Generator-based Effects (Effect.do / Effect.gen)
# =============================================================================

class EffectGen:
    """Helper for generator-based effects (Effect.gen)."""
    
    def __init__(self, gen: Callable[[], AsyncGenerator[Any, Any]]):
        self._gen = gen
    
    def __call__(self) -> Effect[Any, Any, Any]:
        async def run_gen():
            gen = self._gen()
            result = None
            try:
                while True:
                    effect = await gen.asend(result)
                    if isinstance(effect, Effect):
                        result = await effect._run()
                    else:
                        result = effect
            except StopAsyncIteration:
                return result
        return Effect(run_gen)


def gen(gen_func: Callable[[], AsyncGenerator[Any, Any]]) -> Effect[Any, Any, Any]:
    """Create effect from generator (Effect.gen)."""
    effect_gen = EffectGen(gen_func)
    return effect_gen()


# =============================================================================
# Retry Policy (Enhanced)
# =============================================================================

@dataclass
class RetryPolicy:
    """Configurable retry policy (mirrors Effect.RetryPolicy)."""
    max_attempts: int = 3
    base_delay: float = 1.0
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
            delay *= (0.5 + random.random())
        return delay
    
    def with_max_attempts(self, n: int) -> "RetryPolicy":
        return RetryPolicy(max_attempts=n, base_delay=self.base_delay, 
                          max_delay=self.max_delay, exponential_base=self.exponential_base, jitter=self.jitter)
    
    def with_exponential_backoff(self, base: float = 2.0) -> "RetryPolicy":
        return RetryPolicy(max_attempts=self.max_attempts, base_delay=self.base_delay,
                          max_delay=self.max_delay, exponential_base=base, jitter=self.jitter)


DEFAULT_RETRY_POLICY = RetryPolicy()
AGGRESSIVE_RETRY_POLICY = RetryPolicy(max_attempts=5, base_delay=0.5, max_delay=60.0)
CONSERVATIVE_RETRY_POLICY = RetryPolicy(max_attempts=2, base_delay=2.0, max_delay=10.0)


# =============================================================================
# Cancellation
# =============================================================================

class CancellationToken:
    """Token for cooperative cancellation (Effect.CancellationToken)."""
    def __init__(self):
        self._cancelled = False
        self._callbacks: List[Callable[[], None]] = []
    
    @property
    def cancelled(self) -> bool:
        return self._cancelled
    
    def cancel(self) -> None:
        self._cancelled = True
        for cb in self._callbacks:
            try:
                cb()
            except Exception:
                pass
    
    def register(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._callbacks.append(callback)
        return lambda: self._callbacks.remove(callback) if callback in self._callbacks else None
    
    def throw_if_cancelled(self) -> None:
        if self._cancelled:
            raise CancellationError("Operation cancelled")


# =============================================================================
# Resource Management (Effect.acquireRelease, Effect.acquireUseRelease)
# =============================================================================

@dataclass
class Resource(Generic[A]):
    """Managed resource with acquire/release (Effect.acquireRelease)."""
    acquire: Callable[[], Awaitable[A]]
    release: Callable[[A], Awaitable[None]]
    name: str = "resource"
    
    async def __aenter__(self) -> A:
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
    acquire: Callable[[], Awaitable[A]],
    release: Callable[[A], Awaitable[None]],
    name: str = "resource",
) -> AsyncGenerator[A, None]:
    """Context manager for managed resources (Effect.acquireRelease)."""
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


def acquire_release[A](
    acquire: Callable[[], Awaitable[A]],
    release: Callable[[A], Awaitable[None]],
    name: str = "resource"
) -> Resource[A]:
    """Create resource with acquire/release (Effect.acquireRelease)."""
    return Resource(acquire=acquire, release=release, name=name)


async def acquire_use_release[A, B](
    acquire: Callable[[], Awaitable[A]],
    use: Callable[[A], Awaitable[B]],
    release: Callable[[A], Awaitable[None]],
    name: str = "resource"
) -> B:
    """Acquire, use, release in one effect (Effect.acquireUseRelease)."""
    async with managed_resource(acquire, release, name) as resource:
        return await use(resource)


# =============================================================================
# Scope - Resource Lifecycle (Effect.Scope)
# =============================================================================

@dataclass
class Scope:
    """
    Resource scope for managing lifecycles (Effect.Scope).
    Resources added to scope are released when scope closes.
    """
    _resources: List[Callable[[], Awaitable[None]]] = field(default_factory=list)
    _closed: bool = False
    
    def add_finalizer(self, finalizer: Callable[[], Awaitable[None]]) -> None:
        """Add finalizer to be run on scope close."""
        self._resources.append(finalizer)
    
    async def close(self) -> None:
        """Close scope, running all finalizers in reverse order."""
        if self._closed:
            return
        self._closed = True
        for finalizer in reversed(self._resources):
            try:
                await finalizer()
            except Exception as e:
                logger.error("scope_finalizer_failed", error=str(e))
    
    async def __aenter__(self) -> "Scope":
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


def make_scope() -> Scope:
    """Create new scope (Effect.Scope.make)."""
    return Scope()


async def with_scope[A](f: Callable[[Scope], Awaitable[A]]) -> A:
    """Run effect with fresh scope (Effect.withScope)."""
    async with make_scope() as scope:
        return await f(scope)


# =============================================================================
# Layer - Dependency Injection (Effect.Layer)
# =============================================================================

@runtime_checkable
class Service(Protocol):
    """Marker protocol for services."""
    pass


@dataclass
class Layer(Generic[R]):
    """
    Layer for dependency injection (Effect.Layer).
    Builds up environment of services.
    """
    build: Callable[[], Awaitable[Dict[str, Any]]]
    requirements: Dict[str, type] = field(default_factory=dict)
    provides: Dict[str, Any] = field(default_factory=dict)
    
    def __or__(self, other: "Layer") -> "Layer":
        """Merge layers (Layer.merge / | operator)."""
        async def merged_build():
            env1 = await self.build()
            env2 = await other.build()
            return {**env1, **env2}
        return Layer(build=merged_build)
    
    def provide(self, **services) -> "Layer":
        """Add services to layer."""
        async def new_build():
            env = await self.build()
            for key, value in services.items():
                if callable(value) and not isinstance(value, type):
                    env[key] = await value()
                else:
                    env[key] = value
            return env
        return Layer(build=new_build)
    
    async def build_env(self) -> Dict[str, Any]:
        """Build the environment."""
        return await self.build()


def layer(build: Callable[[], Awaitable[Dict[str, Any]]]) -> Layer:
    """Create layer from build function."""
    return Layer(build=build)


def empty_layer() -> Layer:
    """Create empty layer."""
    async def build():
        return {}
    return Layer(build=build)


# =============================================================================
# Fiber - Concurrent Execution (Effect.Fiber)
# =============================================================================

@dataclass
class Fiber(Generic[A, E]):
    """Background computation handle (Effect.Fiber)."""
    _task: asyncio.Task
    
    async def await_(self) -> A:
        """Wait for fiber to complete (Fiber.await)."""
        return await self._task
    
    async def join(self) -> A:
        """Alias for await."""
        return await self.await_()
    
    def interrupt(self) -> "Effect[None, Never, Any]":
        """Interrupt fiber (Fiber.interrupt)."""
        async def interrupt_op():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        return Effect(interrupt_op)
    
    def interrupt_as(e: Exception) -> "Effect[None, Never, Any]":
        """Interrupt fiber with specific error."""
        async def interrupt_op():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                raise e
        return Effect(interrupt_op)
    
    @property
    def done(self) -> bool:
        return self._task.done()


def fork[A, E](effect: Effect[A, E, Any]) -> Effect[Fiber[A, E], Never, Any]:
    """Fork effect into background fiber (Effect.fork)."""
    return succeed(effect.fork())


def fork_daemon[A, E](effect: Effect[A, E, Any]) -> Effect[Fiber[A, E], Never, Any]:
    """Fork effect as daemon (Effect.forkDaemon)."""
    return fork(effect)


# =============================================================================
# Supervisor - Fiber Management (Effect.Supervisor)
# =============================================================================

class Supervisor:
    """Manages child fibers (Effect.Supervisor)."""
    
    def __init__(self):
        self._fibers: List[asyncio.Task] = []
        self._shutdown = False
    
    def supervise(self, effect: Effect[Any, Any, Any]) -> Fiber[Any, Any]:
        """Supervise an effect (run in background, track for cleanup)."""
        fiber = effect.fork()
        self._fibers.append(fiber._task)
        return fiber
    
    async def shutdown(self) -> None:
        """Shutdown all supervised fibers."""
        if self._shutdown:
            return
        self._shutdown = True
        for task in self._fibers:
            task.cancel()
        await asyncio.gather(*self._fibers, return_exceptions=True)
    
    async def __aenter__(self) -> "Supervisor":
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.shutdown()


def make_supervisor() -> Supervisor:
    """Create supervisor (Effect.Supervisor.make)."""
    return Supervisor()


async def with_supervisor[A](f: Callable[[Supervisor], Awaitable[A]]) -> A:
    """Run with supervisor (Effect.withSupervisor)."""
    async with make_supervisor() as supervisor:
        return await f(supervisor)


# =============================================================================
# Parallel Operations (Effect.all, Effect.forEach, etc.)
# =============================================================================

async def all_effects[A, E, R](*effects: Effect[A, E, R]) -> List[A]:
    """Run all effects in parallel, fail fast (Effect.all)."""
    return await asyncio.gather(*[e._run() for e in effects])


async def all_effects_succeed[A, E, R](*effects: Effect[A, E, R]) -> List[A]:
    """Run all effects, collect successes (Effect.allSucceed)."""
    results = await asyncio.gather(*[e._run() for e in effects], return_exceptions=True)
    return [r for r in results if not isinstance(r, Exception)]


async def for_each[A, B, E, R](
    items: List[A],
    f: Callable[[A], Effect[B, E, R]],
    concurrency: Optional[int] = None
) -> List[B]:
    """Map effect over items with concurrency control (Effect.forEach)."""
    if concurrency is None:
        effects = [f(item) for item in items]
        return await all_effects(*effects)
    
    # Bounded concurrency
    semaphore = asyncio.Semaphore(concurrency)
    
    async def bounded(item: A) -> B:
        async with semaphore:
            return await f(item)._run()
    
    return await asyncio.gather(*[bounded(item) for item in items])


async def filter_effect[A, E, R](
    items: List[A],
    f: Callable[[A], Effect[bool, E, R]]
) -> List[A]:
    """Filter items using effect predicate (Effect.filter)."""
    results = await asyncio.gather(*[f(item)._run() for item in items])
    return [item for item, keep in zip(items, results) if keep]


async def partition_effect[A, E, R](
    items: List[A],
    f: Callable[[A], Effect[bool, E, R]]
) -> tuple[List[A], List[A]]:
    """Partition items using effect predicate (Effect.partition)."""
    results = await asyncio.gather(*[f(item)._run() for item in items])
    passed = [item for item, keep in zip(items, results) if keep]
    failed = [item for item, keep in zip(items, results) if not keep]
    return passed, failed


# =============================================================================
# Observability / Spans (Effect.withLogSpan)
# =============================================================================

@dataclass
class Span:
    """Observability span (Effect.Span)."""
    name: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    parent: Optional["Span"] = None
    children: List["Span"] = field(default_factory=list)
    
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


_span_context = SpanContext()


def get_span_context() -> SpanContext:
    return _span_context


@asynccontextmanager
async def span(name: str, attributes: Optional[Dict[str, Any]] = None) -> AsyncGenerator[Span, None]:
    """Create a span (Effect.withLogSpan)."""
    async with _span_context.span(name, attributes) as s:
        yield s


# =============================================================================
# Metrics Collection
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


def with_metrics(name: str) -> Callable[[Callable[..., Awaitable[A]]], Callable[..., Awaitable[A]]]:
    """Decorator to automatically record metrics."""
    def decorator(func: Callable[..., Awaitable[A]]) -> Callable[..., Awaitable[A]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> A:
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
# Effect Combinators (more Effect TS patterns)
# =============================================================================

def zip_effects[A, E, R](*effects: Effect[A, E, R]) -> Effect[List[A], E, R]:
    """Run effects in parallel, return list (Effect.zip)."""
    async def zipped():
        return await asyncio.gather(*[e._run() for e in effects])
    return Effect(zipped)


def all_effects_par[A, E, R](effects: List[Effect[A, E, R]]) -> Effect[List[A], E, R]:
    """Run all effects in parallel (Effect.all)."""
    return zip_effects(*effects)


def race_effects[A, E, R](*effects: Effect[A, E, R]) -> Effect[A, E, R]:
    """Return first completed result (Effect.race)."""
    async def raced():
        done, pending = await asyncio.wait(
            [asyncio.create_task(e._run()) for e in effects],
            return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        return done.pop().result()
    return Effect(raced)


def first_success[A, E, R](*effects: Effect[A, E, R]) -> Effect[A, E, R]:
    """Return first successful result (Effect.firstSuccessOf)."""
    async def first_succeed():
        for effect in effects:
            try:
                return await effect._run()
            except Exception:
                continue
        raise Exception("All effects failed")
    return Effect(first_succeed)


# =============================================================================
# Tool Execution Effect (with full runtime)
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
    
    def to_effect(self, executor: Callable[[str, Dict[str, Any], str, Optional[str]], Awaitable[Dict[str, Any]]]) -> Effect[Dict[str, Any], EffectError, Any]:
        """Convert to Effect."""
        async def execute():
            async with span(f"tool.{self.tool_id}", {
                "tool_id": self.tool_id,
                "execution_target": self.execution_target,
                "timeout_seconds": self.timeout_seconds,
            }) as s:
                start_time = time.time()
                
                try:
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
        
        return Effect(execute)


# =============================================================================
# Helper Functions for Error Handling
# =============================================================================

def with_cause(error: Exception, cause: Exception, context: Optional[Dict[str, Any]] = None) -> EffectError:
    """Wrap error with cause (Effect.cause)."""
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
# Example Usage & Testing
# =============================================================================

if __name__ == "__main__":
    async def example():
        # Example 1: Basic effect composition
        @with_metrics("example.operation")
        async def unreliable_operation(x: int) -> str:
            import random
            if random.random() < 0.7:
                raise TransientError("Random failure")
            return f"Success: {x}"
        
        effect = async_effect(unreliable_operation).retry(DEFAULT_RETRY_POLICY).timeout(10.0)
        result = await effect.run()
        print(f"Result: {result}")
        
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
        
        results = await all_effects(async_effect(op1), async_effect(op2))
        print(f"Parallel results: {results}")
        
        # Example 5: Generator-based effects (Effect.gen)
        @gen
        async def workflow():
            result1 = await async_effect(op1)()
            result2 = await async_effect(op2)()
            return f"{result1}, {result2}"
        
        result = await workflow()
        print(f"Gen result: {result}")
        
        # Example 6: Scope for resource lifecycle
        async with make_scope() as scope:
            resource = acquire_release(
                acquire=lambda: asyncio.sleep(0.1) or "resource",
                release=lambda r: asyncio.sleep(0.05)
            )
            scope.add_finalizer(lambda: resource.release(resource.value) if hasattr(resource, 'value') else asyncio.sleep(0))
        
        # Example 7: Layer for DI
        config_layer = empty_layer().provide(
            db_url="postgresql://localhost/db",
            api_key="secret"
        )
        env = await config_layer.build_env()
        print(f"Env: {env}")
        
        # Example 8: Supervisor for fiber management
        async with make_supervisor() as supervisor:
            fiber = supervisor.supervise(async_effect(lambda: asyncio.sleep(1) or "done"))
            await asyncio.sleep(0.5)
            # Fiber will be cleaned up on exit
    
    asyncio.run(example())


# =============================================================================
# Export
# =============================================================================

__all__ = [
    # Core Types
    "Effect",
    "EffectError",
    "TransientError",
    "PermanentError",
    "CancellationError",
    "TimeoutError",
    "ResourceError",
    "Never",
    # Constructors
    "succeed",
    "fail",
    "async_effect",
    "sync_effect",
    "try_effect",
    "suspend",
    "gen",
    "with_timeout",
    # Retry
    "RetryPolicy",
    "DEFAULT_RETRY_POLICY",
    "AGGRESSIVE_RETRY_POLICY",
    "CONSERVATIVE_RETRY_POLICY",
    # Cancellation
    "CancellationToken",
    # Resources
    "Resource",
    "managed_resource",
    "acquire_release",
    "acquire_use_release",
    # Scope
    "Scope",
    "make_scope",
    "with_scope",
    # Layer
    "Layer",
    "layer",
    "empty_layer",
    # Fiber
    "Fiber",
    "fork",
    "fork_daemon",
    # Supervisor
    "Supervisor",
    "make_supervisor",
    "with_supervisor",
    # Parallel
    "all_effects",
    "all_effects_succeed",
    "for_each",
    "filter_effect",
    "partition_effect",
    # Observability
    "Span",
    "SpanContext",
    "get_span_context",
    "span",
    # Metrics
    "EffectMetrics",
    "get_metrics",
    "record_metrics",
    "with_metrics",
    # Combinators
    "zip_effects",
    "all_effects_par",
    "race_effects",
    "first_success",
    # Tool Execution
    "ToolExecution",
    # Error Handling
    "with_cause",
    "as_transient",
    "as_permanent",
]