"""Shared fixtures and smoke test for DeepEval-based workflow tests.

The plan specifies that the smoke test lives here (tests/deepeval/conftest.py)
rather than in a dedicated test file. Pytest discovers `test_*` functions in
conftest.py when invoked explicitly with the path, e.g.:
    pytest tests/deepeval/conftest.py::test_deepeval_import -v

The fixtures `deepeval_enabled` and `skip_if_no_deepeval_key` are consumed by
sibling test files added in later tasks (correctness/hallucination/toxicity).

Note: this directory intentionally has no `__init__.py` so that pytest imports
this conftest by path. A `tests/deepeval/__init__.py` would make it a top-level
package named `deepeval`, shadowing the PyPI `deepeval` library.
"""

import os

import pytest


@pytest.fixture(scope="session")
def deepeval_enabled():
    """Check if DeepEval is enabled via DEEPEVAL_API_KEY env var."""
    return os.getenv("DEEPEVAL_API_KEY") is not None


@pytest.fixture
def skip_if_no_deepeval_key(deepeval_enabled):
    """Skip test if DeepEval API key not configured."""
    if not deepeval_enabled:
        pytest.skip("DeepEval API key not configured")


def test_deepeval_import():
    """Smoke test - verify DeepEval can be imported and LLMTestCase constructed."""
    import deepeval
    from deepeval.metrics import AnswerRelevancyMetric  # noqa: F401
    from deepeval.test_case import LLMTestCase

    # Guard against a future regression where a stray tests/deepeval/__init__.py
    # (or tests/__init__.py) makes this directory shadow the PyPI `deepeval`.
    assert "site-packages" in (deepeval.__file__ or ""), (
        f"Expected to import the installed deepeval library, got {deepeval.__file__}"
    )

    test_case = LLMTestCase(
        input="What is 2+2?",
        actual_output="4",
        expected_output="4",
    )

    assert test_case.input == "What is 2+2?"
    assert test_case.actual_output == "4"
