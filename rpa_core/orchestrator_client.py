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

    def set_success(self):
        self._client.set_transaction_status(self.id, "Successful")

    def set_failed(self, error_type: str = "Application", message: str = ""):
        self._client.set_transaction_status(self.id, "Failed", error_type=error_type, message=message)


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

    def get_asset(self, name: str) -> str:
        url = f"{self.orchestrator_url.rstrip('/')}/api/robot/assets/{name}"
        resp = requests.get(url, headers=self._headers(), timeout=10)
        if resp.status_code == 404:
            raise ApplicationException(f"Asset '{name}' not found on Orchestrator")
        resp.raise_for_status()
        return resp.json().get("value", "")

    def add_queue_item(self, queue_name: str, data: dict, reference: Optional[str] = None) -> dict:
        url = f"{self.orchestrator_url.rstrip('/')}/api/robot/queues/{queue_name}/items"
        payload = {"data": data, "reference": reference}
        resp = requests.post(url, json=payload, headers=self._headers(), timeout=10)
        if resp.status_code == 409:
            raise BusinessRuleException(f"Duplicate queue reference '{reference}' in queue '{queue_name}'")
        resp.raise_for_status()
        return resp.json()

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

    def set_transaction_status(self, item_id: str, status_val: str, error_type: Optional[str] = None, message: Optional[str] = None):
        url = f"{self.orchestrator_url.rstrip('/')}/api/robot/queues/items/{item_id}/status"
        payload = {"status": status_val, "error_type": error_type, "message": message}
        resp = requests.patch(url, json=payload, headers=self._headers(), timeout=10)
        resp.raise_for_status()

    def log(self, message: str, level: str = "Info"):
        # Prints to stdout for the Execution Agent's LogStreamer to intercept
        print(f"[{level.upper()}] {message}", flush=True)
