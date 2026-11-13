"""Versioned reservation world, capability dispatcher, and replay verifier."""
import hashlib
import json
from copy import deepcopy

VERSION = 1
LIMIT = 10
FAULTS = ("none", "before_commit", "lost_ack")
POLICIES = ("reconcile", "blind_retry", "ollama")


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def fixture(seed):
    if type(seed) is not int or not 0 <= seed <= 999999:
        raise ValueError("seed must be an integer from 0 to 999999")
    pool = ["atlas", "cedar", "delta"]
    offset = int(digest(seed)[:8], 16) % len(pool)
    units = 1 + seed % 3
    return {"request": {"pool": pool[offset], "units": units},
            "stock": {name: 3 * units for name in pool}, "receipts": []}


def action(tool, **args):
    return {"tool": tool, "args": args}


def dispatch(world, call, fault, injected):
    """Only validated data capabilities touch the run-private world."""
    if not isinstance(call, dict) or set(call) != {"tool", "args"}:
        return {"error": "invalid_action"}, False
    name, args = call["tool"], call["args"]
    if not isinstance(args, dict):
        return {"error": "invalid_arguments"}, False
    if name in ("inspect", "finish") and not args:
        if name == "inspect":
            return {"stock": world["stock"].copy(), "receipts": deepcopy(world["receipts"])}, False
        return {"finished": True}, False
    if name != "reserve" or set(args) != {"pool", "units"}:
        return {"error": "capability_denied"}, False
    pool, units = args["pool"], args["units"]
    if not isinstance(pool, str) or pool not in world["stock"] or type(units) is not int or not 1 <= units <= 9:
        return {"error": "invalid_arguments"}, False
    if units > world["stock"][pool]:
        return {"error": "insufficient_stock"}, False
    inject = fault != "none" and not injected
    if inject and fault == "before_commit":
        return {"error": "timeout"}, True
    world["stock"][pool] -= units
    receipt = {"id": len(world["receipts"]) + 1, "pool": pool, "units": units}
    world["receipts"].append(receipt)
    if inject:
        return {"error": "timeout"}, True
    return {"receipt": receipt.copy()}, False


def baseline(policy, request, history):
    if not history:
        return action("inspect")
    last = history[-1]["observation"]
    if "receipt" in last or last.get("receipts"):
        return action("finish")
    if policy == "reconcile" and last.get("error") == "timeout":
        return action("inspect")
    return action("reserve", **request)


def event(world, call, fault, injected, number):
    before = digest(world)
    observation, hit = dispatch(world, call, fault, injected)
    return {"step": number, "action": call, "observation": observation,
            "fault_injected": hit, "before": before, "after": digest(world)}


def grade(initial, world, events):
    request = initial["request"]
    expected = initial["stock"].copy()
    expected[request["pool"]] -= request["units"]
    receipts = world["receipts"]
    checks = {"single_matching_receipt": receipts == [dict(id=1, **request)],
              "inventory_conserved": world["stock"] == expected,
              "agent_finished": bool(events and events[-1]["observation"].get("finished"))}
    return {"passed": all(checks.values()), "checks": checks, "steps": len(events),
            "writes": len(receipts), "timeouts": sum(e["observation"].get("error") == "timeout" for e in events)}


def execute(seed, policy, fault, decide=None, model=None):
    if policy not in POLICIES or fault not in FAULTS:
        raise ValueError("unknown policy or fault")
    if policy == "ollama" and decide is None:
        raise ValueError("local model is disabled")
    initial = fixture(seed)
    world, history, events = deepcopy(initial), [], []
    injected = False
    for step in range(1, LIMIT + 1):
        call = (decide(deepcopy(initial["request"]), deepcopy(history)) if policy == "ollama"
                else baseline(policy, initial["request"], history))
        record = event(world, call, fault, injected, step)
        events.append(record)
        history.append({"action": deepcopy(call), "observation": deepcopy(record["observation"])})
        injected |= record["fault_injected"]
        if record["observation"].get("finished"):
            break
    trace = {"version": VERSION, "seed": seed, "policy": policy, "model": model,
             "fault": fault, "initial": initial, "events": events, "final": world,
             "metrics": grade(initial, world, events)}
    return dict(trace, checksum=digest(trace))


def replay(trace):
    def mismatch(at):
        return {"verified": False, "divergence": at}
    if trace["version"] != VERSION:
        return mismatch("version")
    initial = fixture(trace["seed"])
    if initial != trace["initial"]:
        return mismatch("fixture")
    world, injected = deepcopy(initial), False
    events = trace["events"]
    if not 1 <= len(events) <= LIMIT:
        return mismatch("step_budget")
    for index, recorded in enumerate(events, 1):
        actual = event(world, recorded["action"], trace["fault"], injected, index)
        if actual != recorded:
            return mismatch(f"step {index}")
        injected |= actual["fault_injected"]
        if actual["observation"].get("finished") and index != len(events):
            return mismatch("after_finish")
    if len(events) < LIMIT and not events[-1]["observation"].get("finished"):
        return mismatch("early_stop")
    if world != trace["final"] or grade(initial, world, events) != trace["metrics"]:
        return mismatch("evaluation")
    if digest({k: v for k, v in trace.items() if k != "checksum"}) != trace["checksum"]:
        return mismatch("checksum")
    return {"verified": True, "steps": len(events), "checksum": trace["checksum"]}
