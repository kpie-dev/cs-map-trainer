import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic-scenarios.json"


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text())
