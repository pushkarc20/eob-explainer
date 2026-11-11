import pytest

from healthcore.privacy.detector import PiiDetector


@pytest.fixture(scope="session")
def detector() -> PiiDetector:
    return PiiDetector()
