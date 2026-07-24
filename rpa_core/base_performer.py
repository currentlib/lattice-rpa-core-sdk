import time
import traceback
import logging
from typing import Optional, Any
from rpa_core.exceptions import BusinessRuleException, ApplicationException
from rpa_core.orchestrator_client import OrchestratorClient, TransactionItem

logger = logging.getLogger("rpa_core")


class BasePerformer:
    """
    Base Performer class for RPA automations.
    Responsible for processing transaction items from Orchestrator Queues in a resilient loop.
    """
    QUEUE_NAME: str = ""

    def __init__(self, orchestrator_client: Optional[OrchestratorClient] = None):
        self.orch = orchestrator_client or OrchestratorClient()
        self.stats = {
            "total": 0,
            "successful": 0,
            "business_exceptions": 0,
            "application_exceptions": 0,
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

    def add_queue_item(self, queue_name: str, data: dict[str, Any], reference: Optional[str] = None) -> dict:
        """Helper to add an item to another queue from performer."""
        return self.orch.add_queue_item(queue_name=queue_name, data=data, reference=reference)

    def setup(self):
        """Executed ONCE at startup (Init phase). Override in subclass."""
        pass

    def process(self, item: TransactionItem):
        """Executed for EACH queue transaction item. Override in subclass."""
        raise NotImplementedError("Subclasses must implement process(item)")

    def cleanup(self):
        """Executed ONCE at the end, regardless of fatal errors. Override in subclass."""
        pass

    def run(self):
        """Execute full Performer state machine loop."""
        if not self.QUEUE_NAME:
            raise ValueError("QUEUE_NAME must be specified in subclass of BasePerformer")

        start_ts = time.time()
        self.stats["start_time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_ts))

        self.log(f"=== Starting Robot Execution for Queue: '{self.QUEUE_NAME}' ===")
        try:
            self.log("=== Phase 1: Setup ===")
            self.setup()
        except Exception as e:
            self.log(f"Setup failed: {e}\n{traceback.format_exc()}", level="Error")
            self._safe_cleanup()
            raise

        self.log("=== Phase 2: Transaction Loop ===")

        try:
            while True:
                if self.orch.should_stop():
                    self.log("Received graceful stop signal. Halting transaction loop.", level="Warning")
                    break

                item = self.orch.get_transaction_item(self.QUEUE_NAME)
                if not item:
                    self.log("No more transaction items found. Exiting transaction loop.")
                    break

                self.stats["total"] += 1
                self.log(f"Processing transaction item ID: {item.id} (Reference: {item.reference})")

                try:
                    output_data = self.process(item)
                    
                    # Support returning dict output directly from process(item)
                    if isinstance(output_data, dict):
                        item.set_success(output=output_data)
                    else:
                        item.set_success()
                        
                    self.stats["successful"] += 1
                    self.log(f"Item {item.id} processed successfully.")

                except BusinessRuleException as bre:
                    self.stats["business_exceptions"] += 1
                    self.log(f"Business Rule Exception on item {item.id}: {bre}", level="Error")
                    item.set_failed(error_type="Business", message=str(bre))

                except ApplicationException as ape:
                    self.stats["application_exceptions"] += 1
                    self.log(f"Application Exception on item {item.id}: {ape}", level="Error")
                    item.set_failed(error_type="Application", message=str(ape))

                except Exception as e:
                    self.stats["application_exceptions"] += 1
                    stack_msg = traceback.format_exc()
                    self.log(f"Unhandled Exception on item {item.id}: {e}\n{stack_msg}", level="Error")
                    item.set_failed(error_type="Application", message=f"{e}\n{stack_msg}")

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
        self.log("            PERFORMER EXECUTION SUMMARY           ")
        self.log("==================================================")
        self.log(f" Target Queue          : {self.QUEUE_NAME}")
        self.log(f" Total Processed Items : {self.stats['total']}")
        self.log(f" Successful Items      : {self.stats['successful']}")
        self.log(f" Business Exceptions   : {self.stats['business_exceptions']}")
        self.log(f" Application Exceptions: {self.stats['application_exceptions']}")
        self.log(f" Execution Duration    : {self.stats['elapsed_seconds']} seconds")
        self.log("==================================================")
