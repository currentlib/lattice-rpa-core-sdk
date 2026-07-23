import os
import sys
import logging
import requests
from typing import Any, Optional
from rpa_core.exceptions import BusinessRuleException, ApplicationException

logger = logging.getLogger("rpa_core")


def _load_local_env_file():
    """Simple zero-dependency .env file loader for local developer debugging."""
    search_dirs = [os.getcwd(), os.path.dirname(os.getcwd())]
    for d in search_dirs:
        env_path = os.path.join(d, ".env")
        if os.path.isfile(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k and k not in os.environ:
                                os.environ[k] = v
            except Exception as e:
                logger.debug(f"Failed loading local .env file: {e}")
            break


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
        _load_local_env_file()

        self.orchestrator_url = (orchestrator_url or os.environ.get("ORCHESTRATOR_URL", "http://localhost:8000")).rstrip("/")
        self.job_token = job_token or os.environ.get("JOB_TOKEN", "")
        self.orchestrator_token = os.environ.get("ORCHESTRATOR_TOKEN", "")
        self.folder_id = os.environ.get("FOLDER_ID", "")
        self.dev_folder_name = os.environ.get("DEV_FOLDER_NAME", os.environ.get("FOLDER_NAME", "Default"))

        self.is_local_dev = not bool(self.job_token)

        if self.is_local_dev and not self.orchestrator_token:
            logger.warning(
                "[Local Dev Mode] Missing ORCHESTRATOR_TOKEN! Set ORCHESTRATOR_TOKEN in environment or .env file."
            )

        if self.is_local_dev and self.orchestrator_token:
            self._resolve_folder_id()

    def _headers(self) -> dict[str, str]:
        if self.job_token:
            return {
                "X-Job-Token": self.job_token,
                "Content-Type": "application/json",
            }
        return {
            "Authorization": f"Bearer {self.orchestrator_token}",
            "Content-Type": "application/json",
        }

    def _resolve_folder_id(self):
        if self.folder_id:
            return
        try:
            url = f"{self.orchestrator_url}/api/folders"
            resp = requests.get(url, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                folders = resp.json()
                for f in folders:
                    if f.get("name") == self.dev_folder_name:
                        self.folder_id = f.get("id")
                        logger.info(f"[Local Dev Mode] Resolved folder '{self.dev_folder_name}' -> ID: {self.folder_id}")
                        return
                if folders:
                    self.folder_id = folders[0].get("id")
                    logger.info(f"[Local Dev Mode] Using default folder '{folders[0].get('name')}' -> ID: {self.folder_id}")
        except Exception as e:
            logger.debug(f"Failed resolving folder_id: {e}")

    def get_asset_details(self, name: str) -> dict[str, Any]:
        """Fetch asset details dictionary from Orchestrator."""
        if not self.is_local_dev:
            url = f"{self.orchestrator_url}/api/robot/assets/{name}"
            resp = requests.get(url, headers=self._headers(), timeout=10)
            if resp.status_code == 404:
                raise ApplicationException(f"Asset '{name}' not found on Orchestrator")
            resp.raise_for_status()
            return resp.json()
        else:
            # Local Dev Mode: Fetch via Folder API
            if not self.folder_id:
                self._resolve_folder_id()
            url = f"{self.orchestrator_url}/api/folders/{self.folder_id}/assets"
            resp = requests.get(url, headers=self._headers(), timeout=10)
            resp.raise_for_status()
            assets = resp.json()
            for a in assets:
                if a.get("name") == name:
                    return a
            raise ApplicationException(f"Asset '{name}' not found in folder '{self.dev_folder_name}'")

    def get_asset(self, name: str) -> str:
        """Fetch asset value as string."""
        details = self.get_asset_details(name)
        return details.get("value", "")

    def get_credential(self, name: str) -> str:
        """Fetch credential asset decrypted secret value."""
        return self.get_asset(name)

    def get_asset_int(self, name: str, default: int = 0) -> int:
        """Fetch asset value parsed as integer."""
        try:
            val = self.get_asset(name)
            return int(val)
        except Exception:
            return default

    def get_asset_float(self, name: str, default: float = 0.0) -> float:
        """Fetch asset value parsed as float."""
        try:
            val = self.get_asset(name)
            return float(val)
        except Exception:
            return default

    def get_asset_bool(self, name: str) -> bool:
        """Fetch asset value parsed as boolean."""
        try:
            val = self.get_asset(name).strip().lower()
            return val in ("true", "1", "yes")
        except Exception:
            return False

    def get_asset_json(self, name: str) -> Any:
        """Fetch asset value parsed as JSON."""
        import json
        val = self.get_asset(name)
        return json.loads(val)

    def add_queue_item(self, queue_name: str, data: dict, reference: Optional[str] = None) -> dict:
        """Push transaction item into Orchestrator Queue."""
        if not self.is_local_dev:
            url = f"{self.orchestrator_url}/api/robot/queues/{queue_name}/items"
            payload = {"data": data, "reference": reference}
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=10)
            if resp.status_code == 409:
                raise BusinessRuleException(f"Duplicate queue reference '{reference}' in queue '{queue_name}'")
            resp.raise_for_status()
            return resp.json()
        else:
            # Local Dev Mode: Resolve queue_id via folder API
            if not self.folder_id:
                self._resolve_folder_id()
            q_url = f"{self.orchestrator_url}/api/folders/{self.folder_id}/queues"
            q_resp = requests.get(q_url, headers=self._headers(), timeout=10)
            q_resp.raise_for_status()
            queues = q_resp.json()
            target_queue = next((q for q in queues if q.get("name") == queue_name), None)

            if not target_queue:
                raise ApplicationException(f"Queue '{queue_name}' not found in folder '{self.dev_folder_name}'")

            item_url = f"{self.orchestrator_url}/api/folders/{self.folder_id}/queues/{target_queue['id']}/items"
            payload = {"data": data, "reference": reference}
            resp = requests.post(item_url, json=payload, headers=self._headers(), timeout=10)
            if resp.status_code == 409:
                raise BusinessRuleException(f"Duplicate queue reference '{reference}' in queue '{queue_name}'")
            resp.raise_for_status()
            return resp.json()

    def add_queue_items_bulk(self, queue_name: str, items: list[dict[str, Any]]) -> dict[str, int]:
        """Push multiple queue items into Orchestrator Queue."""
        total = len(items)
        added = 0
        skipped = 0

        for raw_item in items:
            if isinstance(raw_item, dict) and "data" in raw_item and isinstance(raw_item["data"], dict):
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
                self.log(f"Skipped duplicate queue item (reference: '{reference}') in queue '{queue_name}'", level="Warning")
            except Exception as e:
                self.log(f"Error adding queue item to queue '{queue_name}': {e}", level="Error")
                raise

        return {"total": total, "added": added, "skipped": skipped}

    def get_transaction_item(self, queue_name: str) -> Optional[TransactionItem]:
        """Fetch next New queue item via SKIP LOCKED."""
        url = f"{self.orchestrator_url}/api/robot/queues/{queue_name}/next"
        resp = requests.get(url, headers=self._headers(), timeout=10)
        if resp.status_code in (204, 404) or not resp.text:
            return None
        resp.raise_for_status()
        data = resp.json()
        if not data or not isinstance(data, dict) or "id" not in data:
            return None

        return TransactionItem(
            item_id=data["id"],
            queue_id=data["queue_id"],
            reference=data.get("reference"),
            data=data.get("data", {}),
            retry_count=data.get("retry_count", 0),
            client=self,
        )

    def set_transaction_status(self, item_id: str, status: str, error_type: Optional[str] = None, message: Optional[str] = None, output: Optional[dict] = None):
        """Update transaction item status (Successful/Failed)."""
        url = f"{self.orchestrator_url}/api/robot/queues/items/{item_id}/status"
        payload = {
            "status": status,
            "error_type": error_type,
            "message": message,
            "output": output,
        }
        resp = requests.patch(url, json=payload, headers=self._headers(), timeout=10)
        resp.raise_for_status()

    def log(self, message: str, level: str = "Info"):
        """Log message to Orchestrator or stdout in Local Dev Mode."""
        # Always output to local stdout for clear visibility
        prefix = "[LOCAL DEV]" if self.is_local_dev else "[PROD]"
        print(f"[{level.upper()}] {prefix} {message}", flush=True)

        if self.job_token:
            try:
                url = f"{self.orchestrator_url}/api/robot/logs"
                payload = {"message": message, "level": level}
                requests.post(url, json=payload, headers=self._headers(), timeout=5)
            except Exception:
                pass
