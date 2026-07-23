import os
import unittest
import tempfile
from rpa_core import (
    BaseDispatcher,
    BasePerformer,
    BusinessRuleException,
    ApplicationException,
    retry,
    load_csv,
    save_csv,
    load_json,
    save_json,
    mask_secret,
)


class TestUtils(unittest.TestCase):
    def test_mask_secret(self):
        self.assertEqual(mask_secret("secret1234"), "******1234")
        self.assertEqual(mask_secret("123"), "***")
        self.assertEqual(mask_secret(""), "")

    def test_retry_decorator(self):
        attempts = 0

        @retry(max_attempts=3, delay=0.01, backoff=1.0)
        def unstable_func():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ValueError("Temporary failure")
            return "success"

        result = unstable_func()
        self.assertEqual(result, "success")
        self.assertEqual(attempts, 3)

    def test_csv_helpers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.csv")
            data = [
                {"invoice_num": "1001", "amount": "1500"},
                {"invoice_num": "1002", "amount": "3200"},
            ]
            save_csv(filepath, data)
            loaded = load_csv(filepath)
            self.assertEqual(loaded, data)

    def test_json_helpers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.json")
            data = {"key": "value", "items": [1, 2, 3]}
            save_json(filepath, data)
            loaded = load_json(filepath)
            self.assertEqual(loaded, data)


class MockOrchestratorClient:
    def __init__(self):
        self.logs = []
        self.queue = []
        self.assets = {
            "MaxThreshold": "5000",
            "CRM_KEY": "secret_api_key_123",
            "EnableDebug": "true",
            "Rate": "1.5",
        }

    def log(self, msg, level="Info"):
        self.logs.append((level, msg))

    def get_asset_details(self, name):
        if name in self.assets:
            return {"name": name, "value": self.assets[name], "value_type": "Text"}
        raise ApplicationException(f"Asset '{name}' not found")

    def get_asset(self, name):
        return self.get_asset_details(name)["value"]

    def get_credential(self, name):
        return self.get_asset(name)

    def get_asset_int(self, name, default=0):
        val = self.get_asset(name)
        return int(val)

    def get_asset_float(self, name, default=0.0):
        val = self.get_asset(name)
        return float(val)

    def get_asset_bool(self, name):
        return self.get_asset(name).lower() == "true"

    def get_asset_json(self, name):
        import json
        return json.loads(self.get_asset(name))

    def add_queue_item(self, queue_name, data, reference=None):
        for existing in self.queue:
            if reference and existing.get("reference") == reference:
                raise BusinessRuleException("Duplicate reference")
        self.queue.append({"queue_name": queue_name, "data": data, "reference": reference})
        return {"id": "mock-id-1"}

    def add_queue_items_bulk(self, queue_name, items):
        added = 0
        skipped = 0
        for item in items:
            ref = item.get("reference")
            data = item.get("data", item)
            try:
                self.add_queue_item(queue_name, data, reference=ref)
                added += 1
            except BusinessRuleException:
                skipped += 1
        return {"total": len(items), "added": added, "skipped": skipped}


class SampleDispatcher(BaseDispatcher):
    QUEUE_NAME = "Invoices"

    def setup(self):
        self.threshold = self.get_asset_int("MaxThreshold")

    def dispatch(self):
        return [
            {"data": {"invoice_num": "101", "amount": 1000}, "reference": "INV-101"},
            {"data": {"invoice_num": "102", "amount": 2000}, "reference": "INV-102"},
            {"data": {"invoice_num": "101", "amount": 1000}, "reference": "INV-101"},  # Duplicate
        ]


class TestDispatcherAndPerformer(unittest.TestCase):
    def test_dispatcher_flow(self):
        client = MockOrchestratorClient()
        dispatcher = SampleDispatcher(orchestrator_client=client)
        dispatcher.run()

        self.assertEqual(dispatcher.stats["total"], 3)
        self.assertEqual(dispatcher.stats["added"], 2)
        self.assertEqual(dispatcher.stats["skipped"], 1)
        self.assertEqual(len(client.queue), 2)


if __name__ == "__main__":
    unittest.main()
