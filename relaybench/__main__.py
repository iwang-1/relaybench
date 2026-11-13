import argparse
import json

from .engine import FAULTS, execute, replay
from .server import server
from .store import Store


def main():
    parser = argparse.ArgumentParser(description="RelayBench agent reliability lab")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--db", default=".relaybench/runs.sqlite3")
    serve.add_argument("--model", help="installed Ollama model tag")
    matrix = commands.add_parser("matrix")
    matrix.add_argument("--seeds", type=int, default=12)
    args = parser.parse_args()
    if args.command == "matrix":
        if not 1 <= args.seeds <= 10000:
            parser.error("--seeds must be between 1 and 10000")
        results = []
        for policy in ("blind_retry", "reconcile"):
            for fault in FAULTS:
                passed = verified = 0
                for seed in range(args.seeds):
                    trace = execute(seed, policy, fault)
                    passed += trace["metrics"]["passed"]
                    verified += replay(trace)["verified"]
                results.append(dict(policy=policy, fault=fault, runs=args.seeds, passed=passed, verified=verified))
        print(json.dumps(results, indent=2))
    else:
        with server(args.port, Store(args.db), args.model) as http:
            print(f"RelayBench listening on http://127.0.0.1:{http.server_port}", flush=True)
            http.serve_forever()


if __name__ == "__main__":
    main()
