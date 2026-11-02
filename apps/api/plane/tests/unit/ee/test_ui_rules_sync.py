import json
import re
from pathlib import Path

import pytest

from plane.ee.work_item_types.constants import PARENT_RULES

# apps/api/plane/tests/unit/ee -> repo root is 6 levels up (apps/api is the container's /code).
_CANDIDATES = [p / "apps/web/ee/work-item-types/constants.ts" for p in Path(__file__).resolve().parents]


def _ui_rules():
    path = next((p for p in _CANDIDATES if p.exists()), None)
    if path is None:
        pytest.skip("apps/web not available (backend-only checkout/container)")
    body = re.search(r"PARENT_RULES_UI[^=]*=\s*(\{.*?\});", path.read_text(encoding="utf-8"), re.S).group(1)
    body = re.sub(r"(\w+):", r'"\1":', body)  # quote keys
    body = re.sub(r",\s*([}\]])", r"\1", body)  # drop trailing commas
    return json.loads(body)


@pytest.mark.unit
def test_ui_parent_rules_match_backend():
    expected = {k.value: sorted(v.value for v in vals) for k, vals in PARENT_RULES.items()}
    assert {k: sorted(v) for k, v in _ui_rules().items()} == expected
