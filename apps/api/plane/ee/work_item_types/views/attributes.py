from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.db.models import Project
from plane.ee.models import Attribute, AttributeOption, AttributeTemplate, AttributeValue
from plane.ee.work_item_types.exceptions import WorkItemValidationError

from ..serializers.attribute import AttributeOptionSerializer, AttributeSerializer
from .templates import check_type, save_unique

READ = allow_permission([ROLE.ADMIN, ROLE.MEMBER])
WRITE = allow_permission([ROLE.ADMIN])


def _attrs(slug, project_id):
    return Attribute.objects.filter(workspace__slug=slug, project_id=project_id).prefetch_related("options")


def _workspace_id(slug, project_id):
    return Project.objects.values_list("workspace_id", flat=True).get(pk=project_id, workspace__slug=slug)


def _out(slug, project_id, pk):
    return AttributeSerializer(_attrs(slug, project_id).get(pk=pk)).data


class AttributeListEndpoint(BaseAPIView):
    @READ
    def get(self, request, slug, project_id):
        qs = _attrs(slug, project_id)
        if request.query_params.get("issue_type_id"):
            qs = qs.filter(issue_type_id=request.query_params["issue_type_id"])
        return Response(AttributeSerializer(qs, many=True).data)

    @WRITE
    def post(self, request, slug, project_id):
        s = AttributeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        check_type(slug, s.validated_data["issue_type"])
        a = save_unique(s, project_id=project_id, workspace_id=_workspace_id(slug, project_id))
        return Response(_out(slug, project_id, a.pk), status=status.HTTP_201_CREATED)


class AttributeDetailEndpoint(BaseAPIView):
    @WRITE
    def patch(self, request, slug, project_id, pk):
        a = _attrs(slug, project_id).get(pk=pk)
        s = AttributeSerializer(a, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        check_type(slug, s.validated_data.get("issue_type"))
        v = s.validated_data
        retyped = "field_type" in v and v["field_type"] != a.field_type
        if a.is_system and (retyped or ("name" in v and v["name"] != a.name) or "issue_type" in v):
            raise WorkItemValidationError("system_attribute_locked", "System attributes cannot be renamed or retyped")
        if retyped and AttributeValue.objects.filter(attribute=a).exists():
            raise WorkItemValidationError("type_change_blocked", "Attribute already has values")
        save_unique(s)
        return Response(_out(slug, project_id, pk))

    @WRITE
    def delete(self, request, slug, project_id, pk):
        a = _attrs(slug, project_id).get(pk=pk)
        if a.is_system:
            raise WorkItemValidationError("system_attribute_locked", "System attributes cannot be deleted")
        a.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AttributeReorderEndpoint(BaseAPIView):
    @WRITE
    def post(self, request, slug, project_id):
        ids = request.data.get("ids")
        if not isinstance(ids, list):
            raise WorkItemValidationError("invalid_ids", "ids must be a list")
        with transaction.atomic():
            for i, pk in enumerate(ids, start=1):
                _attrs(slug, project_id).filter(pk=pk).update(sort_order=i * 10000)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AttributeApplyTemplateEndpoint(BaseAPIView):
    @WRITE
    def post(self, request, slug, project_id):
        t = AttributeTemplate.objects.prefetch_related("options").get(
            pk=request.data.get("template_id"), workspace__slug=slug
        )
        # Copy only: source_template is a reference and is never read back.
        with transaction.atomic():
            s = AttributeSerializer(
                data={
                    "issue_type": request.data.get("issue_type_id"),
                    "name": t.name,
                    "description": t.description,
                    "field_type": t.field_type,
                    "is_required": t.is_required,
                    "default_value": t.default_value,
                    "settings": t.settings,
                    "sort_order": t.sort_order,
                }
            )
            s.is_valid(raise_exception=True)
            check_type(slug, s.validated_data["issue_type"])
            a = save_unique(s, project_id=project_id, workspace_id=t.workspace_id, source_template=t)
            AttributeOption.objects.bulk_create(
                AttributeOption(
                    attribute=a,
                    name=o.name,
                    sort_order=o.sort_order,
                    is_active=o.is_active,
                    color=o.color,
                    is_default=o.is_default,
                )
                for o in t.options.all()
            )
        return Response(_out(slug, project_id, a.pk), status=status.HTTP_201_CREATED)


class AttributeOptionListEndpoint(BaseAPIView):
    @WRITE
    def post(self, request, slug, project_id, pk):
        a = _attrs(slug, project_id).get(pk=pk)
        s = AttributeOptionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save(attribute=a)
        return Response(s.data, status=status.HTTP_201_CREATED)


class AttributeOptionDetailEndpoint(BaseAPIView):
    @WRITE
    def patch(self, request, slug, project_id, pk, option_id):
        a = _attrs(slug, project_id).get(pk=pk)
        o = AttributeOption.objects.get(pk=option_id, attribute=a)
        s = AttributeOptionSerializer(o, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)

    @WRITE
    def delete(self, request, slug, project_id, pk, option_id):
        a = _attrs(slug, project_id).get(pk=pk)
        AttributeOption.objects.get(pk=option_id, attribute=a).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
