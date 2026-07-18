# Sensorium and Compute Crystal Architecture Decisions

## SADR-001: Observation and actuation remain separate

Status: accepted contract.

Sensor adapters emit evidence. They do not own process, socket, file, network,
or deployment actuators. The permanent sequence is observe, interpret,
recommend, authorize, act, verify, and seal.

## SADR-002: A PID is not a process identity

Status: accepted contract.

Serialized ProcessLease identity binds boot, observed PID, process start time,
executable digest, cgroup, namespaces, parent identity, and owner scope. A pidfd
is live internal state and its integer value is never serialized as identity.

## SADR-003: Crystal Bus uses credentialed message-preserving local transport

Status: accepted for Phase S4.

The local bus uses AF_UNIX/SOCK_SEQPACKET. Peer credentials, ProcessLease,
executable digest, cgroup/workspace scope, ARDA state, and capability lease are
conjunctive. Peer credentials alone are insufficient.

## SADR-004: Crystal capsules are immutable transport without ambient authority

Status: accepted for Phase S4.

A sealed memfd protects capsule immutability and lifecycle. It does not grant
execution authority or confidentiality. The receiver independently checks
identity, seals, digest, signature, policy, expiry, and capability lease.

## SADR-005: Equivalence requires sound reviewed rewrite evidence

Status: accepted for Phase S7.

Semantic similarity never creates an equivalence edge. E-graph rewrites are
versioned, scoped, reviewed, and supported by a proof or independent verifier.
Hard policy and applicability constraints run before cost extraction.
