from setuptools import setup, find_packages

setup(
    name="rpa_core",
    version="0.4.0",
    description="Enterprise Python SDK with BaseDispatcher & BasePerformer Frameworks for Lattice RPA Orchestrator",
    author="Lattice Team",
    packages=find_packages(),
    install_requires=[
        "requests>=2.31.0",
    ],
    python_requires=">=3.11",
)
