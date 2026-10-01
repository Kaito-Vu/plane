# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Production settings + EE plugin. Enable with DJANGO_SETTINGS_MODULE=plane.settings.ee"""

from .production import *  # noqa

INSTALLED_APPS = [*INSTALLED_APPS, "plane.ee"]  # noqa
ROOT_URLCONF = "plane.ee.urls"
