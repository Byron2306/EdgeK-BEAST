#!/usr/bin/env node
/**
 * Effect TS runtime server for BEAST.
 *
 * Newline-delimited JSON-RPC over stdio. Python sends an *effect program*
 * (plain data, no functions) and this process executes it with the real
 * `effect` package, giving Python BEAST access to Effect concurrency,
 * retry/schedule, timeout, resource (acquire/release) and fiber semantics.
 *
 * Leaf operations that need to touch BEAST state are declared as
 * { type: "call", op, args } and executed by calling back into Python over
 * HTTP (the Python bridge hosts a small loopback callback server).
 */
import { Effect, Schedule, Fiber, Duration } from "effect"
import { createInterface } from "node:readline"

const fibers = new Map()
let fiberSeq = 0

function scheduleOf(spec = {}) {
  const cfg = spec.params ?? spec
  switch (spec.type ?? "recurs") {
    case "exponential":
      return Schedule.exponential(Duration.millis(cfg.baseMs ?? 10))
    case "spaced":
      return Schedule.spaced(Duration.millis(cfg.delayMs ?? 10))
    case "fixed":
      return Schedule.fixed(Duration.millis(cfg.delayMs ?? 10))
    case "recurs":
    default:
      return Schedule.recurs(cfg.count ?? 3)
  }
}

function callOp(node) {
  const url = node.url
  return Effect.tryPromise({
    try: async () => {
      const res = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ op: node.op, args: node.args ?? {} }),
        signal: AbortSignal.timeout(node.timeoutMs ?? 60000),
      })
      const payload = await res.json()
      if (!payload.ok) throw new Error(payload.error?.message ?? payload.error ?? "operation failed")
      return payload.value
    },
    catch: (e) => (e instanceof Error ? e : new Error(String(e))),
  })
}

function build(node) {
  if (!node || typeof node !== "object") throw new Error("invalid effect node")
  switch (node.type) {
    case "succeed":
      return Effect.succeed(node.value ?? null)
    case "fail":
      return Effect.fail(new Error(node.message ?? "effect failed"))
    case "sleep":
      return Effect.sleep(Duration.millis(node.ms ?? 0)).pipe(Effect.as(null))
    case "as":
      return build(node.effect).pipe(Effect.as(node.value ?? null))
    case "call":
      return callOp(node)
    case "zip":
      return Effect.all((node.effects ?? []).map(build), { concurrency: "unbounded" })
    case "sequence":
      return Effect.all((node.effects ?? []).map(build), { concurrency: 1 })
    case "race":
      return Effect.raceAll((node.effects ?? []).map(build))
    case "retry":
      return Effect.retry(build(node.effect), scheduleOf(node.schedule))
    case "timeout":
      return Effect.timeout(build(node.effect), Duration.millis(node.ms ?? 0))
    case "resource":
      return Effect.acquireRelease(build(node.acquire), () => build(node.release ?? { type: "succeed" })).pipe(
        Effect.flatMap(() => build(node.use ?? { type: "succeed" })),
        Effect.scoped,
      )
    case "fork": {
      const child = build(node.effect)
      return Effect.sync(() => {
        const fiberId = `fiber_${++fiberSeq}`
        fibers.set(fiberId, Effect.runFork(child))
        return { fiberId }
      })
    }
    case "join": {
      const fiber = fibers.get(node.fiberId)
      if (!fiber) return Effect.fail(new Error(`unknown fiber: ${node.fiberId}`))
      return Effect.promise(() => Effect.runPromise(Fiber.join(fiber)))
    }
    case "interrupt": {
      const fiber = fibers.get(node.fiberId)
      if (!fiber) return Effect.fail(new Error(`unknown fiber: ${node.fiberId}`))
      return Effect.promise(async () => {
        await Effect.runPromise(Fiber.interrupt(fiber))
        fibers.delete(node.fiberId)
        return null
      })
    }
    default:
      throw new Error(`unknown effect type: ${node.type}`)
  }
}

function errorPayload(error) {
  return {
    message: error instanceof Error ? error.message : String(error),
    tag: (error && error._tag) || (error && error.constructor && error.constructor.name) || "Error",
  }
}

async function handle(request) {
  const id = request.id ?? null
  switch (request.op) {
    case "ping":
      return { id, ok: true, value: { pong: true, effect: "4.x" } }
    case "run": {
      try {
        const value = await Effect.runPromise(build(request.program))
        return { id, ok: true, value: value ?? null }
      } catch (error) {
        return { id, ok: false, error: errorPayload(error) }
      }
    }
    case "shutdown":
      return { id, ok: true, value: null, shutdown: true }
    default:
      return { id, ok: false, error: { message: `unknown op: ${request.op}`, tag: "ProtocolError" } }
  }
}

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity })
let pending = 0
let closed = false

function maybeExit() {
  if (closed && pending === 0) process.exit(0)
}

rl.on("line", (line) => {
  const text = line.trim()
  if (!text) return
  let request
  try {
    request = JSON.parse(text)
  } catch (error) {
    process.stdout.write(JSON.stringify({ id: null, ok: false, error: { message: "invalid json", tag: "ProtocolError" } }) + "\n")
    return
  }
  pending++
  handle(request)
    .then((response) => {
      process.stdout.write(JSON.stringify(response) + "\n")
      if (response.shutdown) {
        closed = true
        rl.close()
      }
    })
    .catch((error) => {
      process.stdout.write(JSON.stringify({ id: request.id ?? null, ok: false, error: errorPayload(error) }) + "\n")
    })
    .finally(() => {
      pending--
      maybeExit()
    })
})

rl.on("close", () => {
  closed = true
  maybeExit()
})
