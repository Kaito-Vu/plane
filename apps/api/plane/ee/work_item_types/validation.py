# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from rest_framework.exceptions import ValidationError

from plane.db.models import Issue, IssueType, Project
from plane.db.models.issue_type import ProjectIssueType
from plane.ee.work_item_types.rules import TypeInfo, creates_cycle, hierarchy_error


def _info(issue_type) -> TypeInfo:
    return TypeInfo(str(issue_type.id), int(issue_type.level), issue_type.is_epic)


def resolve_default_type_id(project_id):
    return (
        ProjectIssueType.objects.filter(project_id=project_id, is_default=True)
        .values_list("issue_type_id", flat=True)
        .first()
    )


def _type_info(type_id, project_id) -> TypeInfo | None:
    type_id = type_id or resolve_default_type_id(project_id)
    obj = IssueType.objects.filter(pk=type_id).first() if type_id else None
    return _info(obj) if obj else None


def validate_issue_write(issue) -> None:
    # ponytail: one extra query per Issue save to read the project flag; cache per project if it shows up in profiles
    if not Project.objects.filter(pk=issue.project_id, is_issue_type_enabled=True).exists():
        return
    adding = issue._state.adding
    old = (None, None) if adding else Issue.objects.filter(pk=issue.pk).values_list("type_id", "parent_id").first()
    if adding and issue.type_id is None:
        issue.type_id = resolve_default_type_id(issue.project_id)
    new = (issue.type_id, issue.parent_id)
    if not adding and new == old:
        return
    type_changed = adding or issue.type_id != (old or (None, None))[0]
    parent_changed = adding or issue.parent_id != (old or (None, None))[1]

    if type_changed and issue.type_id is not None:
        allowed = ProjectIssueType.objects.filter(
            project_id=issue.project_id,
            issue_type_id=issue.type_id,
            issue_type__is_active=True,
            deleted_at__isnull=True,
        ).exists()
        if not allowed:
            raise ValidationError({"type_id": "Invalid work item type"})

    child = _type_info(issue.type_id, issue.project_id)
    if child is None:
        return
    parent = None
    if issue.parent_id:
        parent_row = Issue.objects.filter(pk=issue.parent_id, project_id=issue.project_id).first()
        if parent_row is None:
            raise ValidationError({"parent_id": "Invalid parent"})
        parent = _type_info(parent_row.type_id, issue.project_id)
    if type_changed or parent_changed:
        message = hierarchy_error(child, parent)
        if message:
            raise ValidationError({"parent_id": message})
    if parent_changed and issue.parent_id and not adding:
        parent_of = lambda i: Issue.objects.filter(pk=i).values_list("parent_id", flat=True).first()  # noqa: E731
        if creates_cycle(issue.pk, issue.parent_id, parent_of):
            raise ValidationError({"parent_id": "Parent would create a loop"})
    if type_changed and not adding:
        conflicts = []
        for sub in Issue.objects.filter(parent_id=issue.pk)[:200]:
            sub_info = _type_info(sub.type_id, issue.project_id)
            if sub_info and hierarchy_error(sub_info, child):
                conflicts.append(sub.name)
        if conflicts:
            raise ValidationError({"type_id": f"Conflicts with sub-items: {', '.join(conflicts[:5])}"})
