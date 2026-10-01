# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import uuid

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response

from plane.app.views.base import BaseAPIView
from plane.db.models import Issue, IssueType, Workspace
from plane.db.models.issue_type import ProjectIssueType
from plane.ee.work_item_types.serializers import IssueTypeSerializer
from plane.utils.permissions.workspace import WorkspaceOwnerPermission, WorkspaceViewerPermission


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
        serializer = IssueTypeSerializer(data=request.data, context={"workspace": ws})
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
        data = request.data
        changed = any(k in data and data[k] != getattr(obj, k) for k in ("level", "is_epic"))
        if changed and (IssueTypeSerializer().get_is_preset(obj) or Issue.objects.filter(type=obj).exists()):
            return Response(
                {"error": "level and epic flag cannot change for preset types or types in use"},
                status=status.HTTP_409_CONFLICT,
            )
        if data.get("is_active") is False and ProjectIssueType.objects.filter(issue_type=obj, is_default=True).exists():
            return Response({"error": "A project default type cannot be deactivated"}, status=status.HTTP_409_CONFLICT)
        serializer = IssueTypeSerializer(obj, data=data, partial=True, context={"workspace": self.workspace(slug)})
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
            if IssueTypeSerializer().get_is_preset(obj) or obj.is_default:
                return Response({"error": "This type cannot be deleted"}, status=status.HTTP_409_CONFLICT)
            in_use = Issue.objects.filter(type=obj)
            count = in_use.count()
            if count:
                if not target_id:
                    return Response(
                        {"error": "Work items use this type; pass migrate_to", "count": count},
                        status=status.HTTP_409_CONFLICT,
                    )
                target = get_object_or_404(
                    IssueType.objects.exclude(pk=obj.pk), pk=target_id, workspace__slug=slug, is_active=True
                )
                if target.level != obj.level:
                    return Response({"error": "migrate_to must have the same level"}, status=status.HTTP_400_BAD_REQUEST)
                in_use.update(type=target)
            ProjectIssueType.objects.filter(issue_type=obj).delete()
            obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
