# BEAST Sensorium and Proof-Carrying Crystals Research

The research source for this feature is the repository-level
[Sensorium and Proof-Carrying Compute Crystal Plan](../beast-sensorium-proof-carrying-crystal-plan.md),
grounded in the existing BEAST compression, interception, cache, semantic-page,
crystal, lattice, capability, evidence, and network implementations.

The feature is governed by the umbrella
[BEAST DevSecOps, ARDA, Commons, and Control Evidence Master Plan](../beast-devsecops-arda-commons-master-plan.md).
That plan owns cross-system sequencing, ARDA attestation, DevSecOps lanes,
Commons federation, resource governance, and control evidence.

Research conclusion: build an observation-first Sensorium and typed,
proof-carrying Crystal IR without granting execution authority to semantic
similarity, immutable transport, or historical success alone.

The Metatron/ARDA read-only assessment adds a second invariant: a RuntimeEpisode
or crystal may reference an ARDA appraisal, BEAST capability lease, and
Metatron outbound decision, but may never synthesize, refresh, or widen any of
them. See
[Metatron, ARDA, and BEAST Integration Assessment](../metatron-arda-beast-integration-assessment.md).

## Phase S1 targeted research

The in-process retained window uses explicit `threading.RLock` synchronization
rather than relying on GIL behavior or incidental atomicity of container
operations. This keeps multi-step offset, displacement, loss-event, and metric
updates coherent on ordinary and free-threaded Python builds.

Downstream event and episode files are written to a temporary file in the
destination directory, flushed, and installed with `os.replace`. The
filesystem exporter consumes already-sanitized admitted objects; it is not the
runtime bus.

Primary references:

- Python thread-safety guidance:
  <https://docs.python.org/3/howto/free-threading-python.html>
- Python lock context management:
  <https://docs.python.org/3/library/threading.html>
- Atomic same-filesystem replacement:
  <https://docs.python.org/3/library/os.html#os.replace>

## Phase S2 targeted research

Linux pidfds are live references to tasks and are pollable for process exit.
S2 therefore keeps pidfd integers entirely in supervisor memory, binds the
serialized ProcessLease to stable `/proc` observations, and uses one epoll
constellation for lifecycle readiness. Signals are sent through
`pidfd_send_signal`; no integer-PID signal path exists in the supervisor.

For cgroup v2, `cgroup.events` supplies recursive population state and is
pollable, freeze completion is reported through the same event file, and
`cgroup.kill` is a recursive destructive operation. BEAST consequently uses
graceful pidfd termination first and requires a separate destructive approval
receipt before cgroup kill.

Destructive execution is also part of the Sensorium causal record. Retirement
now emits a content-bound descendant snapshot and a verified transition or
payload-safe refusal; cgroup escalation emits verified `populated 0`, an
unconfirmed outcome, or a refusal. Guardian lifecycle transitions remain
ingested from its durable ledger. These events contain hashes, typed descriptor
references, counts, and state transitions—not signatures, raw credentials,
live pidfds, file descriptors, or command text. Sensorium therefore supplies
ordered evidence and negative outcomes while retaining no execution authority.

Isolation claims follow the same rule. The effective cgroup delegation point
must be resolved from `/proc/self/cgroup`; mount-root writability is not a
proxy for systemd delegation. A populated domain cgroup cannot safely enable
new domain controllers under the no-internal-process constraint. BEAST records
that condition as reduced authority and does not move unrelated IDE tasks.
Namespace isolation is proved independently by parent/child inode changes,
private `/proc`, and route inspection. It does not imply cgroup containment or
race-free placement; those require direct birth into a delegated child.

The direct-birth helper uses `clone3(CLONE_INTO_CGROUP)` rather than writing a
running PID to `cgroup.procs`. A gate pipe holds the child before `execveat`
until the parent observes membership. Only inherited descriptors cross the
native interface; executable selection and its digest are authorized before
launch. The executed worker receives an empty environment and no cgroup
descriptor. Sensorium records the worker digest, target descriptor identity,
placement method, membership readback, and receipt digest, but not executable
paths, native stderr, or live descriptor numbers.

The isolated worker is fixed-purpose and accepts no arguments or environment.
It maps only the invoking UID/GID into a new user namespace, establishes mount,
network, and PID namespaces, and becomes PID 1 after the cgroup membership
gate. Network absence is measured through a route-netlink link dump rather
than host-mounted sysfs. A private tmpfs root and private proc mount prevent
ordinary path access to the host root; selected secret paths are checked only
after chroot. Parent-side evidence confirms mount teardown. This still does
not substitute for seccomp, Landlock, a device policy, or resource-controller
enforcement.

Compute Forge must consume isolation as an admission fact, not advertise it as
a static capability string. Its attestation binds the worker and launch
receipt, delegation receipt, proven isolation dimensions, cleanup, enabled
controllers, missing controllers, and authority mode. Scheduler matching then
intersects work requirements with attested controllers. Consequently a
user-delegated forge may execute CPU/memory/PID-bounded work while an
I/O-bounded job remains queued for a system-delegated node.

Moving an already-running process through `cgroup.procs` necessarily uses a
numeric PID. S2 verifies the ProcessLease immediately before and after that
write and reports any drift as failure. Race-free birth directly inside a
mission capsule is a later hardening step using `clone3(CLONE_INTO_CGROUP)`;
S2 does not overclaim that property.

Primary references:

- Python pidfd support:
  <https://docs.python.org/3/library/os.html#os.pidfd_open>
- Python epoll interface:
  <https://docs.python.org/3/library/select.html#edge-and-level-trigger-polling-epoll-objects>
- Linux cgroup v2 lifecycle controls:
  <https://docs.kernel.org/admin-guide/cgroup-v2.html>
- Linux `clone3` cgroup placement:
  <https://man7.org/linux/man-pages/man2/clone.2.html>
