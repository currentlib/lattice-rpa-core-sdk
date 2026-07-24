import os
os.environ["ORCHESTRATOR_URL"] = "http://localhost:8000"
from rpa_core.orchestrator_client import OrchestratorClient
client = OrchestratorClient(job_token="fake")
print("Should stop:", client.should_stop())
