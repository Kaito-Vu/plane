# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.apps import apps
from django.conf import settings

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES


@pytest.mark.unit
def test_plugin_installed_and_urlconf_swapped():
    assert apps.is_installed("plane.ee")
    assert settings.ROOT_URLCONF == "plane.ee.urls"


@pytest.mark.unit
def test_error_codes_registered():
    assert AUTHENTICATION_ERROR_CODES["SSO_NOT_CONFIGURED"] == 6000
    assert AUTHENTICATION_ERROR_CODES["SSO_PROVIDER_ERROR"] == 6001
