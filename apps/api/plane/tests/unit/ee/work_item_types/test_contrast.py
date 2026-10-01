# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.ee.work_item_types.contrast import contrast_ratio
from plane.ee.work_item_types.serializers import IssueTypeSerializer
from plane.db.models import IssueType


@pytest.mark.unit
def test_black_white_is_21():
    assert round(contrast_ratio("#000000", "#FFFFFF"), 2) == 21.0


@pytest.mark.unit
def test_same_colour_is_1():
    assert contrast_ratio("#123456", "#123456") == pytest.approx(1.0)


@pytest.mark.unit
def test_known_pair():
    # #777777 on white is the classic ~4.48:1 pair
    assert round(contrast_ratio("#777777", "#ffffff"), 2) == 4.48


@pytest.mark.unit
@pytest.mark.parametrize(
    "icon,expected",
    [
        ({"color": "#FFFFFF", "background_color": "#FFFFFE"}, True),
        ({"color": "#FFFFFF", "background_color": "#000000"}, False),
        ({"color": "#FFFFFF"}, False),
        (None, False),
    ],
)
def test_low_contrast_flag(workspace, icon, expected):
    logo = {"in_use": "icon", "icon": icon} if icon else {}
    t = IssueType(workspace=workspace, name="X", level=1, logo_props=logo)
    assert IssueTypeSerializer(t).data["low_contrast"] is expected
