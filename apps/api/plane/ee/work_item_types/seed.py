# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.db import transaction

from plane.db.models import DraftIssue, Issue, IssueType, Project
from plane.db.models.issue_type import ProjectIssueType
from plane.ee.work_item_types.presets import EXCLUSIVE, PRESETS, PROCESSES, SHARED, SOURCE


class ProcessChangeBlocked(Exception):
    def __init__(self, message, count=0):
        super().__init__(message)
        self.count = count


def type_usage(type_id, project=None):
    """(issues, drafts) querysets using a type, including archived and soft-deleted (restorable) rows."""
    issues, drafts = Issue.all_objects.filter(type_id=type_id), DraftIssue.all_objects.filter(type_id=type_id)
    if project is not None:
        issues, drafts = issues.filter(project=project), drafts.filter(project=project)
    return issues, drafts


def seed_types(workspace) -> dict:
    """Create the preset types of a workspace once (idempotent). Returns key -> IssueType."""
    result = {}
    with transaction.atomic():
        for key, (name, level, is_epic, icon, color) in PRESETS.items():
            obj, _ = IssueType.objects.get_or_create(
                workspace=workspace,
                external_source=SOURCE,
                external_id=key,
                defaults={
                    "name": name,
                    "level": level,
                    "is_epic": is_epic,
                    "logo_props": {
                        "in_use": "icon",
                        "icon": {"name": icon, "color": "#FFFFFF", "background_color": color},
                    },
                },
            )
            result[key] = obj
    return result


def project_process(project) -> str | None:
    keys = set(
        ProjectIssueType.objects.filter(project=project, issue_type__external_source=SOURCE).values_list(
            "issue_type__external_id", flat=True
        )
    )
    for process, exclusive in EXCLUSIVE.items():
        if exclusive in keys:
            return process
    return None


@transaction.atomic
def apply_process(project, process: str, migrate: bool = False) -> None:
    if process not in PROCESSES:
        raise ValueError(process)
    types = seed_types(project.workspace)
    current = project_process(project)
    if current and current != process:
        old = types[EXCLUSIVE[current]]
        count = Issue.objects.filter(project=project, type=old).count()
        count += DraftIssue.objects.filter(project=project, type=old).count()
        if count and not migrate:
            raise ProcessChangeBlocked(f"{old.name} is still used by work items in this project", count)
        if count:
            new = types[EXCLUSIVE[process]]  # same level (2) as the old exclusive type
            Issue.all_objects.filter(project=project, type=old).update(type=new)
            DraftIssue.all_objects.filter(project=project, type=old).update(type=new)
        ProjectIssueType.objects.filter(project=project, issue_type=old).delete()
    wanted = [*SHARED, EXCLUSIVE[process]]
    ProjectIssueType.objects.filter(project=project, is_default=True).update(is_default=False)
    for key in wanted:
        pit, _ = ProjectIssueType.objects.get_or_create(
            project=project, issue_type=types[key], defaults={"level": types[key].level}
        )
        pit.is_default = key == EXCLUSIVE[process]
        pit.save(update_fields=["is_default"])
    Project.objects.filter(pk=project.pk).update(is_issue_type_enabled=True)
