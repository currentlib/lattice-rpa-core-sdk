import traceback
import logging
from typing import Optional
from rpa_core.exceptions import BusinessRuleException, ApplicationException
from rpa_core.orchestrator_client import OrchestratorClient, TransactionItem

logger = logging.getLogger("rpa_core")


class BasePerformer:
    QUEUE_NAME: str = ""

    def __init__(self, orchestrator_client: Optional[OrchestratorClient] = None):
        self.orch = orchestrator_client or OrchestratorClient()

    def log(self, message: str, level: str = "Info"):
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

    def get_asset_json(self, name: str):
        return self.orch.get_asset_json(name)

    def setup(self):
        """Executed ONCE at startup (Analogous to Init state). Override in subclass."""
        pass

    def process(self, item: TransactionItem):
        """Executed for EACH queue transaction item. Override in subclass."""
        raise NotImplementedError("Subclasses must implement process(item)")

    def cleanup(self):
        """Executed ONCE at the end, regardless of fatal errors. Override in subclass."""
        pass

    def run(self):
        """State Machine loop execution."""
        if not self.QUEUE_NAME:
            raise ValueError("QUEUE_NAME must be specified in subclass of BasePerformer")

        self.log("=== Starting Robot Execution (Init Phase) ===")
        try:
            self.setup()
        except Exception as e:
            self.log(f"Setup failed: {e}\n{traceback.format_exc()}", level="Error")
            self._safe_cleanup()
            raise

        self.log("=== Entering Main Transaction Loop ===")
        processed_count = 0

        try:
            while True:
                item = self.orch.get_transaction_item(self.QUEUE_NAME)
                if not item:
                    self.log("No more transaction items found. Exiting transaction loop.")
                    break

                processed_count += 1
                self.log(f"Processing transaction item ID: {item.id} (Reference: {item.reference})")

                try:
                    self.process(item)
                    item.set_success()
                    self.log(f"Item {item.id} processed successfully.")

                except BusinessRuleException as bre:
                    self.log(f"Business Rule Exception on item {item.id}: {bre}", level="Error")
                    item.set_failed(error_type="Business", message=str(bre))

                except ApplicationException as ape:
                    self.log(f"Application Exception on item {item.id}: {ape}", level="Error")
                    item.set_failed(error_type="Application", message=str(ape))

                except Exception as e:
                    stack_msg = traceback.format_exc()
                    self.log(f"Unhandled Exception on item {item.id}: {e}\n{stack_msg}", level="Error")
                    item.set_failed(error_type="Application", message=f"{e}\n{stack_msg}")

        finally:
            self.log("=== Entering Teardown Phase ===")
            self._safe_cleanup()
            self.log(f"Robot execution completed. Total items processed: {processed_count}")

    def _safe_cleanup(self):
        try:
            self.cleanup()
        except Exception as e:
            self.log(f"Error during cleanup: {e}", level="Error")
