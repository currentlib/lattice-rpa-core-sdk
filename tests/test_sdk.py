import pytest
from unittest.mock import MagicMock
from rpa_core.base_performer import BasePerformer
from rpa_core.exceptions import BusinessRuleException, ApplicationException
from rpa_core.orchestrator_client import TransactionItem


class DummyRobot(BasePerformer):
    QUEUE_NAME = "TestQueue"

    def __init__(self, mock_client, items_to_process):
        super().__init__(orchestrator_client=mock_client)
        self.items = items_to_process
        self.setup_called = False
        self.cleanup_called = False

    def setup(self):
        self.setup_called = True

    def process(self, item):
        val = item.data.get("action")
        if val == "business_fail":
            raise BusinessRuleException("Business validation error")
        elif val == "app_fail":
            raise ApplicationException("Element not found")

    def cleanup(self):
        self.cleanup_called = True


def test_base_performer_flow():
    mock_client = MagicMock()

    item1 = TransactionItem("1", "q1", "ref1", {"action": "success"}, 0, mock_client)
    item2 = TransactionItem("2", "q1", "ref2", {"action": "business_fail"}, 0, mock_client)
    item3 = TransactionItem("3", "q1", "ref3", {"action": "app_fail"}, 0, mock_client)

    mock_client.get_transaction_item.side_effect = [item1, item2, item3, None]

    robot = DummyRobot(mock_client, [item1, item2, item3])
    robot.run()

    assert robot.setup_called is True
    assert robot.cleanup_called is True

    # Item 1 should set success
    mock_client.set_transaction_status.assert_any_call("1", "Successful")

    # Item 2 should set failed with Business error
    mock_client.set_transaction_status.assert_any_call("2", "Failed", error_type="Business", message="Business validation error")

    # Item 3 should set failed with Application error
    mock_client.set_transaction_status.assert_any_call("3", "Failed", error_type="Application", message="Element not found")
