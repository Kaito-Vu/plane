# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import uuid

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response

from plane.app.views.base import BaseAPIView
from plane.db.models import DraftIssue, Issue, IssueType, Project, Workspace
from plane.db.models.issue_type import ProjectIssueType
from plane.ee.work_item_types.serializers import IssueTypeSerializer
from plane.ee.work_item_types.presets import PROCESSES
from plane.ee.work_item_types.seed import ProcessChangeBlocked, apply_process, project_process
from plane.utils.permissions.project import ProjectAdminPermission, ProjectEntityPermission
from plane.utils.permissions.workspace import WorkspaceOwnerPermission, WorkspaceViewerPermission


_TRUE, _FALSE = (True, "true", "1", 1), (False, "false", "0", 0)


def _as_bool(value):
    """Booleans from JSON or form-encoded bodies; None when not a recognisable boolean."""
    if isinstance(value, str):
        value = value.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return None


def _body(request):
    return request.data if hasattr(request.data, "get") else {}


class _WorkspaceTypeBase(BaseAPIView):
    def get_permissions(self):
        cls = WorkspaceViewerPermission if self.request.method == "GET" else WorkspaceOwnerPermission
        return [cls()]

    def workspace(self, slug):
        return get_object_or_404(Workspace, slug=slug)


class WorkItemTypeListEndpoint(_WorkspaceTypeBase):
    def get(self, request, slug):
        qs = IssueType.objects.filter(workspace__slug=slug).order_by("-level", "name")
        return Response(IssueTypeSerializer(qs, many=True).data)

    def post(self, request, slug):
        ws = self.workspace(slug)
        with transaction.atomic():
            # serialize creates per workspace so the cap and unique-name checks cannot race
            Workspace.objects.select_for_update().get(pk=ws.pk)
            serializer = IssueTypeSerializer(data=_body(request), context={"workspace": ws})
            serializer.is_valid(raise_exception=True)
            serializer.save(workspace=ws)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class WorkItemTypeDetailEndpoint(_WorkspaceTypeBase):
    def _get(self, slug, pk):
        return get_object_or_404(IssueType, pk=pk, workspace__slug=slug)

    def get(self, request, slug, pk):
        return Response(IssueTypeSerializer(self._get(slug, pk)).data)

    def patch(self, request, slug, pk):
        obj = self._get(slug, pk)
        data = _body(request)
        if data is not request.data:
            return Response({"error": "Invalid body"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            level_changed = "level" in data and int(data["level"]) != obj.level
        except (TypeError, ValueError):
            return Response({"error": "Invalid level"}, status=status.HTTP_400_BAD_REQUEST)
        epic_changed = "is_epic" in data and _as_bool(data["is_epic"]) is not obj.is_epic
        if (level_changed or epic_changed) and (
            IssueTypeSerializer().get_is_preset(obj) or Issue.objects.filter(type=obj).exists()
        ):
            return Response(
                {"error": "level and epic flag cannot change for preset types or types in use"},
                status=status.HTTP_409_CONFLICT,
            )
        with transaction.atomic():
            ws = Workspace.objects.select_for_update().get(slug=slug)  # serialize renames per workspace
            if (
                _as_bool(data.get("is_active")) is False
                and ProjectIssueType.objects.filter(issue_type=obj, is_default=True).exists()
            ):
                return Response(
                    {"error": "A project default type cannot be deactivated"}, status=status.HTTP_409_CONFLICT
                )
            serializer = IssueTypeSerializer(obj, data=data, partial=True, context={"workspace": ws})
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response(serializer.data)

    def delete(self, request, slug, pk):
        raw = request.query_params.get("migrate_to")
        target_id = None
        if raw:
            try:
                target_id = uuid.UUID(raw)
            except ValueError:
                return Response({"error": "Invalid migrate_to"}, status=status.HTTP_400_BAD_REQUEST)
            if target_id == pk:
                return Response({"error": "Invalid migrate_to"}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            obj = get_object_or_404(IssueType.objects.select_for_update(), pk=pk, workspace__slug=slug)
            if (
                IssueTypeSerializer().get_is_preset(obj)
                or obj.is_default
                or ProjectIssueType.objects.filter(issue_type=obj, is_default=True).exists()
            ):
                return Response({"error": "This type cannot be deleted"}, status=status.HTTP_409_CONFLICT)
            in_use = Issue.objects.filter(type=obj)
            drafts = DraftIssue.objects.filter(type=obj)
            count = in_use.count() + drafts.count()
            if count:
                if not target_id:
                    return Response(
                        {"error": "Work items use this type; pass migrate_to", "count": count},
                        status=status.HTTP_409_CONFLICT,
                    )
                target = get_object_or_404(
                    IssueType.objects.exclude(pk=obj.pk), pk=target_id, workspace__slug=slug, is_active=True
                )
                if target.level != obj.level or target.is_epic != obj.is_epic:
                    return Response(
                        {"error": "migrate_to must have the same level and epic flag"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                using = set(in_use.values_list("project_id", flat=True)) | set(drafts.values_list("project_id", flat=True))
                using.discard(None)
                assigned = set(
                    ProjectIssueType.objects.filter(issue_type=target, project_id__in=using).values_list(
                        "project_id", flat=True
                    )
                )
                if using - assigned:
                    return Response(
                        {"error": "migrate_to must be assigned to every project using this type"},
                        status=status.HTTP_409_CONFLICT,
                    )
                in_use.update(type=target)
                drafts.update(type=target)
            ProjectIssueType.objects.filter(issue_type=obj).delete()
            obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _parse_uuid(raw):
    try:
        return uuid.UUID(raw) if isinstance(raw, str) else None
    except ValueError:
        return None


def _lock_project(project):
    # serialize project-level writes; must be called inside transaction.atomic()
    return Project.objects.select_for_update().get(pk=project.pk)


_INVALID_TYPE = {"error": "Invalid work item type"}


class _ProjectTypeBase(BaseAPIView):
    def get_permissions(self):
        cls = ProjectEntityPermission if self.request.method == "GET" else ProjectAdminPermission
        return [cls()]

    def project_obj(self, slug, project_id):
        return get_object_or_404(Project, pk=project_id, workspace__slug=slug)


class ProjectWorkItemTypesEndpoint(_ProjectTypeBase):
    def get(self, request, slug, project_id):
        project = self.project_obj(slug, project_id)
        rows = ProjectIssueType.objects.filter(project=project).select_related("issue_type")
        types = []
        for r in sorted(rows, key=lambda r: (-r.issue_type.level, r.issue_type.name)):
            data = IssueTypeSerializer(r.issue_type).data
            data["is_project_default"] = r.is_default
            types.append(data)
        return Response(
            {"process": project_process(project), "enabled": project.is_issue_type_enabled, "types": types}
        )

    def post(self, request, slug, project_id):
        project = self.project_obj(slug, project_id)
        process = _body(request).get("process")
        if not isinstance(process, str) or process not in PROCESSES:
            return Response({"error": "process must be scrum or agile"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                project = _lock_project(project)
                apply_process(project, process)
        except ProcessChangeBlocked as e:
            return Response({"error": str(e)}, status=status.HTTP_409_CONFLICT)
        return Response({"process": process}, status=status.HTTP_200_OK)


class ProjectWorkItemTypeAssignEndpoint(_ProjectTypeBase):
    def post(self, request, slug, project_id):
        project = self.project_obj(slug, project_id)
        type_id = _parse_uuid(_body(request).get("type_id"))
        with transaction.atomic():
            _lock_project(project)
            obj = type_id and IssueType.objects.filter(pk=type_id, workspace__slug=slug, is_active=True).first()
            if not obj:
                return Response(_INVALID_TYPE, status=status.HTTP_400_BAD_REQUEST)
            ProjectIssueType.objects.get_or_create(project=project, issue_type=obj, defaults={"level": int(obj.level)})
        return Response({"type_id": str(obj.id)}, status=status.HTTP_200_OK)

    def delete(self, request, slug, project_id, type_id):
        project = self.project_obj(slug, project_id)
        with transaction.atomic():
            _lock_project(project)
            row = get_object_or_404(ProjectIssueType, project=project, issue_type_id=type_id)
            if row.is_default or Issue.objects.filter(project=project, type_id=type_id).exists():
                return Response(
                    {"error": "Type is the project default or still used by work items"},
                    status=status.HTTP_409_CONFLICT,
                )
            row.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectWorkItemTypeDefaultEndpoint(_ProjectTypeBase):
    def post(self, request, slug, project_id):
        project = self.project_obj(slug, project_id)
        type_id = _parse_uuid(_body(request).get("type_id"))
        with transaction.atomic():
            _lock_project(project)
            row = type_id and ProjectIssueType.objects.filter(
                project=project, issue_type_id=type_id, issue_type__is_active=True
            ).first()
            if not row:
                return Response(_INVALID_TYPE, status=status.HTTP_400_BAD_REQUEST)
            ProjectIssueType.objects.filter(project=project, is_default=True).update(is_default=False)
            row.is_default = True
            row.save(update_fields=["is_default"])
        return Response(status=status.HTTP_200_OK)
