import uuid

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.db.models import IssueType, Workspace
from plane.ee.models import AttributeTemplate, AttributeTemplateOption
from plane.ee.work_item_types.exceptions import WorkItemValidationError

from ..serializers.attribute import AttributeTemplateOptionSerializer, AttributeTemplateSerializer

ADMIN = allow_permission([ROLE.ADMIN], level="WORKSPACE")


def save_unique(serializer, **kwargs):
    """Save, mapping the unique-name constraint to a 400."""
    try:
        with transaction.atomic():
            return serializer.save(**kwargs)
    except IntegrityError as e:
        name = getattr(getattr(e.__cause__, "diag", None), "constraint_name", None) or ""
        if not name.endswith("unique_name_when_deleted_at_null"):
            raise
        raise WorkItemValidationError("duplicate_name", "An attribute with this name already exists")


def check_type(slug, issue_type):
    if issue_type is not None and not IssueType.objects.filter(pk=issue_type.pk, workspace__slug=slug).exists():
        raise WorkItemValidationError("invalid_issue_type", "Issue type not in workspace")


OPTION_TYPES = ("select", "multi_select")


def check_options_allowed(field_type):
    if field_type not in OPTION_TYPES:
        raise WorkItemValidationError("options_not_allowed", "Only select/multi_select attributes have options")


def parse_ids(ids):
    try:
        ids = [uuid.UUID(str(i)) for i in ids]
    except (TypeError, ValueError):
        ids = None
    if not ids or len(set(ids)) != len(ids):
        raise WorkItemValidationError("invalid_reorder_ids", "ids must be a non-empty list of unique uuids")
    return ids


def _templates(slug):
    return AttributeTemplate.objects.filter(workspace__slug=slug).prefetch_related("options")


class AttributeTemplateListEndpoint(BaseAPIView):
    @ADMIN
    def get(self, request, slug):
        return Response(AttributeTemplateSerializer(_templates(slug), many=True).data)

    @ADMIN
    def post(self, request, slug):
        s = AttributeTemplateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        check_type(slug, s.validated_data.get("issue_type"))
        t = save_unique(s, workspace=Workspace.objects.get(slug=slug))
        return Response(AttributeTemplateSerializer(t).data, status=status.HTTP_201_CREATED)


class AttributeTemplateDetailEndpoint(BaseAPIView):
    @ADMIN
    def patch(self, request, slug, pk):
        t = _templates(slug).get(pk=pk)
        s = AttributeTemplateSerializer(t, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        check_type(slug, s.validated_data.get("issue_type"))
        save_unique(s)
        return Response(AttributeTemplateSerializer(_templates(slug).get(pk=pk)).data)

    @ADMIN
    def delete(self, request, slug, pk):
        _templates(slug).get(pk=pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AttributeTemplateOptionEndpoint(BaseAPIView):
    @ADMIN
    def post(self, request, slug, pk):
        t = _templates(slug).get(pk=pk)
        check_options_allowed(t.field_type)
        s = AttributeTemplateOptionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save(template=t)
        return Response(s.data, status=status.HTTP_201_CREATED)


class AttributeTemplateOptionDetailEndpoint(BaseAPIView):
    @ADMIN
    def patch(self, request, slug, pk, option_id):
        o = AttributeTemplateOption.objects.get(pk=option_id, template=_templates(slug).get(pk=pk))
        s = AttributeTemplateOptionSerializer(o, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)

    @ADMIN
    def delete(self, request, slug, pk, option_id):
        o = AttributeTemplateOption.objects.get(pk=option_id, template=_templates(slug).get(pk=pk))
        o.is_active = False  # soft delete
        o.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AttributeTemplateReorderEndpoint(BaseAPIView):
    @ADMIN
    def post(self, request, slug):
        ids = parse_ids(request.data.get("ids"))
        if _templates(slug).filter(pk__in=ids).count() != len(ids):
            raise WorkItemValidationError("invalid_reorder_ids", "Unknown template ids")
        with transaction.atomic():
            for i, pk in enumerate(ids, start=1):
                _templates(slug).filter(pk=pk).update(sort_order=i * 10000)
        return Response(status=status.HTTP_204_NO_CONTENT)
