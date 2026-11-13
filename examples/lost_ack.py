"""Print a paired, replay-verified example using the real execution engine."""
import json

from relaybench.engine import execute, replay


def comparison():
    rows = []
    for policy in ("reconcile", "blind_retry"):
        trace = execute(42, policy, "lost_ack")
        assert replay(trace)["verified"]
        rows.append({
            "policy": policy,
            "actions": [event["action"]["tool"] for event in trace["events"]],
            "receipts": trace["final"]["receipts"],
            "passed": trace["metrics"]["passed"],
            "checksum": trace["checksum"],
        })
    return rows


if __name__ == "__main__":
    print(json.dumps(comparison(), indent=2))
