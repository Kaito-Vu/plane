# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.conf import settings

# EE tests only make sense under plane.settings.ee_test (--ds). Otherwise do not collect them.
collect_ignore_glob = [] if "plane.ee" in settings.INSTALLED_APPS else ["sso/*", "test_*.py", "work_item_types/*"]
