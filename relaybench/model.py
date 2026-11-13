"""Optional local model policy. The engine owns tool execution."""
import json
from urllib.request import Request, urlopen

INSTRUCTIONS = """Reserve exactly the requested units in the requested pool, once.
Return one JSON object per turn with keys tool and args.
inspect takes {} and returns inventory and receipts for this request.
reserve takes {pool, units} and creates a new receipt on every successful write.
A timeout has an unknown commit outcome. finish takes {} and ends the run.
You have ten actions. Use only the given request and observed tool responses."""


def local_policy(model):
    def decide(request, history):
        payload = {"model": model, "stream": False, "format": "json", "options": {"temperature": 0},
                   "messages": [{"role": "system", "content": INSTRUCTIONS},
                                {"role": "user", "content": json.dumps({"request": request, "history": history})}]}
        req = Request("http://127.0.0.1:11434/api/chat", json.dumps(payload).encode(),
                      {"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=30) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError("model response too large")
            call = json.loads(json.loads(raw)["message"]["content"])
            if len(json.dumps(call)) > 2048:
                raise ValueError("model action too large")
            return call
        except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
            raise RuntimeError("local model failed to return a bounded JSON action") from exc
    return decide
