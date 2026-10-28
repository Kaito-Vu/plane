from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.db.models import IssueType, Workspace
from plane.ee.models import AttributeTemplate
from plane.ee.work_item_types.exceptions import WorkItemValidationError

from ..serializers.attribute import AttributeTemplateOptionSerializer, AttributeTemplateSerializer

ADMIN = allow_permission([ROLE.ADMIN], level="WORKSPACE")


def save_unique(serializer, **kwargs):
    """Save, mapping the unique-name constraint to a 400."""
    try:
        with transaction.atomic():
            return serializer.save(**kwargs)
    except IntegrityError:
        raise WorkItemValidationError("duplicate_name", "An attribute with this name already exists")


def check_type(slug, issue_type):
    if issue_type is not None and not IssueType.objects.filter(pk=issue_type.pk, workspace__slug=slug).exists():
        raise WorkItemValidationError("invalid_issue_type", "Issue type not in workspace")


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
        s = AttributeTemplateOptionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save(template=t)
        return Response(s.data, status=status.HTTP_201_CREATED)
