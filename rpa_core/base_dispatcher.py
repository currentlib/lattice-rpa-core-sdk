import time
import traceback
import logging
from typing import Optional, Any
from rpa_core.exceptions import BusinessRuleException, ApplicationException
from rpa_core.orchestrator_client import OrchestratorClient

logger = logging.getLogger("rpa_core")


class BaseDispatcher:
    """
    Base Dispatcher class for RPA automations.
    Responsible for fetching input data (from APIs, files, DBs) and populating Orchestrator Queues.
    """
    QUEUE_NAME: str = ""

    def __init__(self, orchestrator_client: Optional[OrchestratorClient] = None):
        self.orch = orchestrator_client or OrchestratorClient()
        self.stats = {
            "total": 0,
            "added": 0,
            "skipped": 0,
            "start_time": None,
            "end_time": None,
            "elapsed_seconds": 0.0,
        }

    def log(self, message: str, level: str = "Info"):
        """Log execution message via OrchestratorClient."""
        self.orch.log(message, level=level)

    def get_asset(self, name: str) -> str:
        return self.orch.get_asset(name)

    def get_credential(self, name: str) -> str:
        return self.orch.get_credential(name)

    def get_asset_int(self, name: str, default: int = 0) -> int:
        return self.orch.get_asset_int(name, default=default)

    def get_asset_float(self, name: str, default: float = 0.0) -> float:
        return self.orch.get_asset_float(name, default=default)

    def get_asset_bool(self, name: str) -> bool:
        return self.orch.get_asset_bool(name)

    def get_asset_json(self, name: str) -> Any:
        return self.orch.get_asset_json(name)

    def add_item(self, data: dict[str, Any], reference: Optional[str] = None) -> bool:
        """
        Add a single transaction item to the target queue.
        Returns True if added successfully, False if duplicate reference skipped.
        """
        if not self.QUEUE_NAME:
            raise ValueError("QUEUE_NAME must be specified before adding queue items.")

        try:
            self.orch.add_queue_item(queue_name=self.QUEUE_NAME, data=data, reference=reference)
            self.stats["added"] += 1
            self.stats["total"] += 1
            self.log(f"Queued item successfully (Reference: '{reference or 'N/A'}')")
            return True
        except BusinessRuleException:
            self.stats["skipped"] += 1
            self.stats["total"] += 1
            self.log(f"Skipped duplicate queue item (Reference: '{reference}')", level="Warning")
            return False

    def add_items_bulk(self, items: list[dict[str, Any]]) -> dict[str, int]:
        """
        Push multiple queue items into the target queue in bulk.
        Returns summary dictionary: {"total": int, "added": int, "skipped": int}
        """
        if not self.QUEUE_NAME:
            raise ValueError("QUEUE_NAME must be specified before adding queue items.")

        res = self.orch.add_queue_items_bulk(queue_name=self.QUEUE_NAME, items=items)
        self.stats["total"] += res["total"]
        self.stats["added"] += res["added"]
        self.stats["skipped"] += res["skipped"]
        self.log(f"Bulk push complete: {res['added']} added, {res['skipped']} skipped out of {res['total']} total items.")
        return res

    def setup(self):
        """Executed ONCE at startup (Init phase). Override in subclass."""
        pass

    def dispatch(self) -> Optional[list[dict[str, Any]]]:
        """
        Main dispatching phase. Either return a list of items to push or push items using self.add_item().
        Override in subclass.
        """
        raise NotImplementedError("Subclasses must implement dispatch()")

    def cleanup(self):
        """Executed ONCE at the end, regardless of errors. Override in subclass."""
        pass

    def run(self):
        """Execute full Dispatcher lifecycle."""
        if not self.QUEUE_NAME:
            raise ValueError("QUEUE_NAME must be specified in subclass of BaseDispatcher")

        start_ts = time.time()
        self.stats["start_time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_ts))

        self.log(f"=== Starting Dispatcher Robot Execution for Queue: '{self.QUEUE_NAME}' ===")
        try:
            self.log("=== Phase 1: Setup ===")
            self.setup()

            self.log("=== Phase 2: Dispatching Queue Items ===")
            dispatched_items = self.dispatch()
            if dispatched_items and isinstance(dispatched_items, list):
                self.add_items_bulk(dispatched_items)

        except Exception as e:
            stack_msg = traceback.format_exc()
            self.log(f"Unhandled Exception in Dispatcher: {e}\n{stack_msg}", level="Error")
            raise
        finally:
            end_ts = time.time()
            self.stats["end_time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_ts))
            self.stats["elapsed_seconds"] = round(end_ts - start_ts, 2)

            self.log("=== Phase 3: Cleanup ===")
            self._safe_cleanup()
            self._print_execution_summary()

    def _safe_cleanup(self):
        try:
            self.cleanup()
        except Exception as e:
            self.log(f"Error during cleanup: {e}", level="Error")

    def _print_execution_summary(self):
        self.log("==================================================")
        self.log("           DISPATCHER EXECUTION SUMMARY           ")
        self.log("==================================================")
        self.log(f" Target Queue  : {self.QUEUE_NAME}")
        self.log(f" Total Evaluated: {self.stats['total']}")
        self.log(f" Added to Queue : {self.stats['added']}")
        self.log(f" Skipped (Dupes): {self.stats['skipped']}")
        self.log(f" Execution Time : {self.stats['elapsed_seconds']} seconds")
        self.log("==================================================")
