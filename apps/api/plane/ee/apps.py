# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _seed_on_license_migrate(sender, **kwargs):
    if sender.label == "license":  # LicenseConfig has no explicit label, so it is "license"
        from plane.ee.sso.config import seed_config

        seed_config()


class EeConfig(AppConfig):
    name = "plane.ee"
    label = "ee"

    def ready(self):
        from plane.ee.sso import errors  # noqa: F401  (registers error codes)

        from plane.ee.work_item_types import signals  # noqa: F401

        post_migrate.connect(_seed_on_license_migrate, dispatch_uid="ee_sso_seed")
