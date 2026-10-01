# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.db.models.signals import pre_save
from django.dispatch import receiver

from plane.db.models import Issue
from plane.ee.work_item_types.validation import validate_issue_write


@receiver(pre_save, sender=Issue, dispatch_uid="ee_work_item_type_validate")
def issue_pre_save(sender, instance, raw=False, **kwargs):
    if not raw:
        validate_issue_write(instance)
