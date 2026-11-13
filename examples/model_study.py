"""Run or verify a small matched local-model study across two tool environments."""
import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

from relaybench.engine import action, baseline, execute, replay
from relaybench.model import INSTRUCTIONS

PUBLISH = """Publish the requested title, preserving the current catalog revision rules.
Return exactly one JSON object with the literal keys "tool" and "args".
Example: {"tool":"read","args":{}}. read takes {} and returns title and revision.
publish takes {title, revision} and succeeds only if revision matches the current catalog.
If publish returns conflict, obtain the current revision and try again. finish takes {}.
You have ten actions. Only publish the requested title."""


INITIAL = PUBLISH.replace('Return exactly one JSON object with the literal keys "tool" and "args".\nExample: {"tool":"read","args":{}}.', "Return exactly one JSON action with tool and args.")
PROMPTS = {"initial": INITIAL, "example": PUBLISH, "completion": PUBLISH + "\nPublish exactly once. Once publish returns published:true, immediately call finish with empty args."}


def model_action(model, prompt, request, history):
    data = {"model": model, "temperature": 0, "max_tokens": 128,
            "messages": [{"role": "system", "content": prompt},
                         {"role": "user", "content": json.dumps(dict(request=request, history=history))}]}
    req = Request("http://127.0.0.1:1234/v1/chat/completions", json.dumps(data).encode(),
                  {"Content-Type": "application/json"})
    with urlopen(req, timeout=120) as response:
        content = json.load(response)["choices"][0]["message"]["content"].strip()
    if content.startswith("```") and content.endswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        return json.loads(content)
    except ValueError:
        return {"invalid_model_output": content}


def catalog(seed, conflict, decide):
    request = {"title": f"Release {seed}"}
    state = {"title": "Draft", "revision": 1 + seed % 5}
    events = []
    writes = 0
    pending = conflict
    for _ in range(10):
        call = decide(request, events)
        obs = {"error": "invalid_action"}
        if call == action("read"):
            obs = state.copy()
        elif call == action("finish"):
            obs = {"finished": True}
        elif isinstance(call, dict) and call.get("tool") == "publish":
            args = call.get("args")
            if isinstance(args, dict) and set(args) == {"revision", "title"} and type(args["revision"]) is int and isinstance(args["title"], str):
                if pending:
                    state["revision"] += 1
                    pending = False
                if args["revision"] != state["revision"]:
                    obs = {"error": "conflict"}
                else:
                    state.update(title=args["title"], revision=state["revision"] + 1)
                    writes += 1
                    obs = {"published": True}
        events.append({"action": call, "observation": obs})
        if obs.get("finished"):
            break
    return dict(events=events, final=state, writes=writes,
                passed=writes == 1 and state["title"] == request["title"] and bool(events[-1]["observation"].get("finished")))


def catalog_reference(request, history):
    if not history or history[-1]["observation"].get("error"):
        return action("read")
    last = history[-1]["observation"]
    if last.get("published"):
        return action("finish")
    return action("publish", title=request["title"], revision=last["revision"])


def trial(task, seed, fault, policy, model, recorded=None, variant="example"):
    actions = iter(recorded) if recorded is not None else None
    def decide(request, history):
        if actions is not None:
            return next(actions)
        if policy == "model":
            return model_action(model, INSTRUCTIONS if task == "reserve" else PROMPTS[variant], request, history)
        if task == "catalog":
            return catalog_reference(request, history)
        return baseline("reconcile", request, history)
    if task == "catalog":
        result = catalog(seed, fault == "conflict", decide)
    else:
        trace = execute(seed, "external", fault, decide, model=model if policy == "model" else None)
        if not replay(trace)["verified"]:
            raise ValueError("reservation replay diverged")
        result = dict(events=[{k:e[k] for k in ("action","observation")} for e in trace["events"]],
                      final=trace["final"], passed=trace["metrics"]["passed"], writes=trace["metrics"]["writes"])
    return dict(task=task, seed=seed, fault=fault, policy=policy, **result)


def verify(report):
    for run in report["runs"]:
        actual = trial(run["task"], run["seed"], run["fault"], run["policy"], report["model"],
                       [e["action"] for e in run["events"]])
        if actual != run:
            raise ValueError("recorded trajectory diverged")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("file", type=Path)
    p.add_argument("--model", help="local LM Studio identifier; omit to verify offline")
    p.add_argument("--variant", choices=PROMPTS, default="example")
    args = p.parse_args()
    if args.model:
        runs = []
        for task, faults in [("reserve", ["none","before_commit","lost_ack"]), ("catalog", ["none","conflict"])]:
            for fault in faults:
                for policy in ("reference", "model"):
                    runs.append(trial(task, 42, fault, policy, args.model, variant=args.variant))
        report = {"model": args.model, "catalog_prompt": PROMPTS[args.variant], "reserve_prompt": INSTRUCTIONS, "temperature": 0, "runs": runs}
        verify(report)
        args.file.write_text(json.dumps(report, indent=2) + "\n")
    else:
        verify(json.loads(args.file.read_text()))
