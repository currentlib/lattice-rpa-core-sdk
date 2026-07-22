from setuptools import setup, find_packages

setup(
    name="rpa_core",
    version="0.1.0",
    description="Developer Python SDK and BasePerformer Framework for RPA Orchestrator",
    author="Lattice Team",
    packages=find_packages(),
    install_requires=[
        "requests>=2.31.0",
    ],
    python_requires=">=3.11",
)
