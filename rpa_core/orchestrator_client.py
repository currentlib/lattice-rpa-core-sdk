import os
import sys
import logging
import requests
from typing import Any, Optional
from rpa_core.exceptions import BusinessRuleException, ApplicationException

logger = logging.getLogger("rpa_core")


class TransactionItem:
    def __init__(self, item_id: str, queue_id: str, reference: Optional[str], data: dict, retry_count: int, client: "OrchestratorClient"):
        self.id = item_id
        self.queue_id = queue_id
        self.reference = reference
        self.data = data
        self.retry_count = retry_count
        self._client = client

    def set_success(self, output: Optional[dict] = None):
        self._client.set_transaction_status(self.id, "Successful", output=output)

    def set_failed(self, error_type: str = "Application", message: str = "", output: Optional[dict] = None):
        self._client.set_transaction_status(self.id, "Failed", error_type=error_type, message=message, output=output)


class OrchestratorClient:
    def __init__(self, orchestrator_url: Optional[str] = None, job_token: Optional[str] = None):
        self.orchestrator_url = orchestrator_url or os.environ.get("ORCHESTRATOR_URL", "http://localhost:8000")
        self.job_token = job_token or os.environ.get("JOB_TOKEN", "")
        
        if not self.job_token:
            logger.warning("JOB_TOKEN environment variable is not set!")

    def _headers(self) -> dict[str, str]:
        return {
            "X-Job-Token": self.job_token,
            "Content-Type": "application/json",
        }

    def get_asset_details(self, name: str) -> dict[str, Any]:
        """Fetch asset details dictionary from Orchestrator."""
        url = f"{self.orchestrator_url.rstrip('/')}/api/robot/assets/{name}"
        resp = requests.get(url, headers=self._headers(), timeout=10)
        if resp.status_code == 404:
            raise ApplicationException(f"Asset '{name}' not found on Orchestrator")
        resp.raise_for_status()
        return resp.json()

    def get_asset(self, name: str) -> str:
        """Fetch asset value as string."""
        details = self.get_asset_details(name)
        return details.get("value", "")

    def get_credential(self, name: str) -> str:
        """Fetch credential asset decrypted secret value."""
        return self.get_asset(name)

    def get_asset_int(self, name: str, default: int = 0) -> int:
        """Fetch asset value parsed as integer."""
        val = self.get_asset(name)
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def get_asset_float(self, name: str, default: float = 0.0) -> float:
        """Fetch asset value parsed as float."""
        val = self.get_asset(name)
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    def get_asset_bool(self, name: str) -> bool:
        """Fetch asset value parsed as boolean."""
        val = self.get_asset(name).strip().lower()
        return val in ("true", "1", "yes", "t", "y", "enabled")

    def get_asset_json(self, name: str) -> Any:
        """Fetch asset value parsed as JSON payload object/dict/list."""
        import json
        val = self.get_asset(name)
        try:
            return json.loads(val)
        except Exception as e:
            raise ApplicationException(f"Asset '{name}' value is not valid JSON: {e}")

    def add_queue_item(self, queue_name: str, data: dict, reference: Optional[str] = None) -> dict:
        url = f"{self.orchestrator_url.rstrip('/')}/api/robot/queues/{queue_name}/items"
        payload = {"data": data, "reference": reference}
        resp = requests.post(url, json=payload, headers=self._headers(), timeout=10)
        if resp.status_code == 409:
            raise BusinessRuleException(f"Duplicate queue reference '{reference}' in queue '{queue_name}'")
        resp.raise_for_status()
        return resp.json()

    def add_queue_items_bulk(self, queue_name: str, items: list[dict[str, Any]]) -> dict[str, int]:
        """
        Pushes multiple items into an Orchestrator Queue.
        Each item element can be a dict with 'data' and optional 'reference', or raw data payload dict.
        Returns summary dictionary: {"total": int, "added": int, "skipped": int}
        """
        total = len(items)
        added = 0
        skipped = 0

        for raw_item in items:
            if "data" in raw_item and isinstance(raw_item["data"], dict):
                data = raw_item["data"]
                reference = raw_item.get("reference")
            else:
                data = raw_item
                reference = raw_item.get("reference") if isinstance(raw_item, dict) else None

            try:
                self.add_queue_item(queue_name=queue_name, data=data, reference=reference)
                added += 1
            except BusinessRuleException:
                skipped += 1
                logger.info(f"Skipped duplicate queue item (reference: '{reference}') in queue '{queue_name}'")
            except Exception as e:
                logger.error(f"Error adding queue item to queue '{queue_name}': {e}")
                raise

        return {"total": total, "added": added, "skipped": skipped}

    def get_transaction_item(self, queue_name: str) -> Optional[TransactionItem]:
        url = f"{self.orchestrator_url.rstrip('/')}/api/robot/queues/{queue_name}/next"
        resp = requests.get(url, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        return TransactionItem(
            item_id=data["id"],
            queue_id=data["queue_id"],
            reference=data.get("reference"),
            data=data.get("data", {}),
            retry_count=data.get("retry_count", 0),
            client=self,
        )

    def set_transaction_status(self, item_id: str, status_val: str, error_type: Optional[str] = None, message: Optional[str] = None, output: Optional[dict] = None):
        url = f"{self.orchestrator_url.rstrip('/')}/api/robot/queues/items/{item_id}/status"
        payload = {"status": status_val, "error_type": error_type, "message": message, "output": output}
        resp = requests.patch(url, json=payload, headers=self._headers(), timeout=10)
        resp.raise_for_status()

    def log(self, message: str, level: str = "Info"):
        # Prints to stdout for the Execution Agent's LogStreamer to intercept
        print(f"[{level.upper()}] {message}", flush=True)
