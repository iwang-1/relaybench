# Execution architecture

A run owns an inventory, one request and an initially empty receipt ledger. Version 1 seeds determine the target pool and quantity. The full initial fixture lives in the trace so a future reader can identify generator drift.

| Component | Owns |
| --- | --- |
| Policy | Selects the next action from the request and visible observations |
| Dispatcher | Validates capability, arguments, inventory and available stock |
| Fault injector | Alters the first eligible write, before mutation or after mutation and before acknowledgment |
| Recorder | Captures the proposed action, observation, injection marker, sequence and before/after state digests |
| Evaluator | Checks the receipt ledger, every pool's final stock and explicit termination |
| Replay verifier | Regenerates the world, executes the recorded decisions and compares every event and the final evaluation |

## Why the two faults matter

The first valid reservation attempt either returns a receipt, times out before inventory changes, or times out after the ledger changes. Both timeouts have identical agent-visible payloads. Injection markers and state hashes are inspector-only evidence. A retry is a new write, and the tool intentionally has no idempotency key. Inspecting the ledger resolves the ambiguity in this single-request world. Concurrent writers and eventually consistent reads would require a different task specification.

## Boundaries and persistence

Policies can request only inspect, reserve and finish. Each run gets private in-memory state and ten action slots. Invalid actions consume a slot. The local model receives JSON data and can never select a network destination or execute code through a tool. Only the optional adapter contacts a fixed loopback model endpoint. The Python policy interface is for trusted in-process adapters.

The loopback HTTP API commits a completed trace as one SQLite row. Concurrent calls use independent SQLite connections. A process crash before persistence discards the in-flight run. Repeating a create request starts a distinct experiment. Model transport or decoding failures return an HTTP error and produce no completed run. Stored runs have no automatic retention limit. This MVP targets a single-user workstation.

## Replay contract

SHA-256 covers canonical JSON with sorted keys and compact separators. IDs and timestamps are excluded from the reproducible payload. Verification checks the version, seed-derived fixture, each transition, step budget, termination, final state, metrics and checksum. The first mismatched transition is reported by index. A digest detects changes relative to the recorded trace. An editor who controls the database can replace a trace and recompute its digest.

## Verification

Unit tests exercise both fault boundaries, denied capabilities, policy isolation, replay divergence, budget exhaustion and the model adapter contract. Integration tests exercise HTTP validation, persistence, replay and concurrent database writes. CI runs the suite on Python 3.11–3.13. For the optional browser smoke test, make Playwright available to Node, install its Chromium browser, start a fresh demo server and run `node docs/browser-demo.cjs`. The script checks the paired comparison, replay, trace expansion and mobile width, then saves the desktop capture.
