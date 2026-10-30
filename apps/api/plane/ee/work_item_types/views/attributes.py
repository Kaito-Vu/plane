from django.db import transaction
from django.db.models import Max
from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.db.models import Project
from plane.db.models.issue_type import ProjectIssueType
from plane.ee.models import Attribute, AttributeOption, AttributeTemplate, AttributeValue
from plane.ee.work_item_types.exceptions import WorkItemValidationError

from ..serializers.attribute import AttributeOptionSerializer, AttributeSerializer
from .templates import check_options_allowed, check_type, parse_ids, save_unique

READ = allow_permission([ROLE.ADMIN, ROLE.MEMBER])
WRITE = allow_permission([ROLE.ADMIN])


def _attrs(slug, project_id):
    return Attribute.objects.filter(workspace__slug=slug, project_id=project_id).prefetch_related("options")


def _workspace_id(slug, project_id):
    return Project.objects.values_list("workspace_id", flat=True).get(pk=project_id, workspace__slug=slug)


def check_project_type(slug, project_id, issue_type):
    check_type(slug, issue_type)
    if (
        issue_type is not None
        and not ProjectIssueType.objects.filter(project_id=project_id, issue_type=issue_type).exists()
    ):
        raise WorkItemValidationError("issue_type_not_in_project", "Issue type is not enabled in this project")


def _option_guard(a):
    if a.is_system and a.system_key != "project_phase":
        raise WorkItemValidationError("system_attribute_locked", "Options of this system attribute are locked")
    check_options_allowed(a.field_type)


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
        check_project_type(slug, project_id, s.validated_data["issue_type"])
        a = save_unique(s, project_id=project_id, workspace_id=_workspace_id(slug, project_id))
        return Response(_out(slug, project_id, a.pk), status=status.HTTP_201_CREATED)


class AttributeDetailEndpoint(BaseAPIView):
    @WRITE
    def patch(self, request, slug, project_id, pk):
        a = _attrs(slug, project_id).get(pk=pk)
        s = AttributeSerializer(a, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        if a.is_system and any(getattr(a, k) != val for k, val in v.items() if k != "is_required"):
            raise WorkItemValidationError("system_attribute_locked", "Only is_required can change on system attributes")
        if "issue_type" in v and v["issue_type"] != a.issue_type:
            raise WorkItemValidationError("attribute_type_immutable", "Attribute issue type cannot change")
        retyped = "field_type" in v and v["field_type"] != a.field_type
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
        ids = parse_ids(request.data.get("ids"))
        qs = _attrs(slug, project_id).filter(pk__in=ids)
        if request.data.get("issue_type_id"):
            qs = qs.filter(issue_type_id=request.data["issue_type_id"])
        if qs.count() != len(ids):
            raise WorkItemValidationError("invalid_reorder_ids", "ids must be attributes of this project/type")
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
                }
            )
            s.is_valid(raise_exception=True)
            it = s.validated_data["issue_type"]
            check_project_type(slug, project_id, it)
            last = _attrs(slug, project_id).filter(issue_type=it).aggregate(m=Max("sort_order"))["m"] or 0
            a = save_unique(
                s, project_id=project_id, workspace_id=t.workspace_id, source_template=t, sort_order=last + 10000
            )
            src = list(t.options.all())
            new_opts = AttributeOption.objects.bulk_create(
                AttributeOption(
                    attribute=a,
                    name=o.name,
                    sort_order=o.sort_order,
                    is_active=o.is_active,
                    color=o.color,
                    is_default=o.is_default,
                )
                for o in src
            )
            # Select default_value holds template option id(s); point them at the copied options.
            id_map = {str(o.pk): str(n.pk) for o, n in zip(src, new_opts)}
            dv = a.default_value
            if isinstance(dv, list):
                a.default_value = [id_map.get(str(v), v) for v in dv]
            elif dv is not None:
                a.default_value = id_map.get(str(dv), dv)
            if a.default_value != dv:
                a.save(update_fields=["default_value"])
        return Response(_out(slug, project_id, a.pk), status=status.HTTP_201_CREATED)


class AttributeOptionListEndpoint(BaseAPIView):
    @WRITE
    def post(self, request, slug, project_id, pk):
        a = _attrs(slug, project_id).get(pk=pk)
        _option_guard(a)
        s = AttributeOptionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save(attribute=a)
        return Response(s.data, status=status.HTTP_201_CREATED)


class AttributeOptionDetailEndpoint(BaseAPIView):
    @WRITE
    def patch(self, request, slug, project_id, pk, option_id):
        a = _attrs(slug, project_id).get(pk=pk)
        _option_guard(a)
        o = AttributeOption.objects.get(pk=option_id, attribute=a)
        s = AttributeOptionSerializer(o, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)

    @WRITE
    def delete(self, request, slug, project_id, pk, option_id):
        a = _attrs(slug, project_id).get(pk=pk)
        _option_guard(a)
        o = AttributeOption.objects.get(pk=option_id, attribute=a)
        o.is_active = False  # soft delete
        o.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)
