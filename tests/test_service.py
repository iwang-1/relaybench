import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path

from relaybench.engine import execute
from relaybench.server import server
from relaybench.store import Store


class StoreTests(unittest.TestCase):
    def test_concurrent_transactions_and_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runs.db"
            store = Store(path)
            trace = execute(3, "reconcile", "lost_ack")
            with ThreadPoolExecutor(max_workers=6) as pool:
                ids = list(pool.map(store.save, [trace] * 12))
            self.assertEqual(len(set(ids)), 12)
            reopened = Store(path)
            self.assertEqual(len(reopened.recent()), 12)
            self.assertEqual(reopened.read(ids[0]), trace)


class ApiTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.http = server(0, Store(Path(tmp.name) / "db"))
        worker = threading.Thread(target=self.http.serve_forever)
        worker.start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(worker.join)
        self.addCleanup(self.http.shutdown)

    def request(self, method, path, data=None, **headers):
        conn = HTTPConnection("127.0.0.1", self.http.server_port, timeout=4)
        try:
            conn.request(method, path, json.dumps(data), {"Content-Type": "application/json", **headers})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_round_trip(self):
        status, run = self.request("POST", "/api/runs", dict(seed=5, policy="blind_retry", fault="lost_ack"))
        self.assertEqual(status, 201)
        path = "/api/runs/" + run["id"]
        self.assertFalse(self.request("GET", path)[1]["metrics"]["passed"])
        self.assertTrue(self.request("POST", path + "/replay", {})[1]["verified"])
        self.assertEqual(self.request("GET", "/api/runs")[1][0]["id"], run["id"])

    def test_rejected_requests_do_not_create_runs(self):
        for data in ({}, [], dict(seed=True, policy="reconcile", fault="none"),
                     dict(seed=0, policy="ollama", fault="none")):
            self.assertEqual(self.request("POST", "/api/runs", data)[0], 400)
        self.assertEqual(self.request("POST", "/api/runs", {}, Origin="http://example.com")[0], 403)
        self.assertEqual(self.request("GET", "/api/runs")[1], [])
