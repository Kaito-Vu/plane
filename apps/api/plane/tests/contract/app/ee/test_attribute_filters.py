import datetime as dt
import json
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status

from plane.db.models import Cycle, Issue, Project, ProjectUserProperty
from plane.ee.models import Attribute, AttributeOption, AttributeValue
from plane.ee.work_item_types.constants import TypeKey
from plane.ee.work_item_types.registry import get_type
from plane.ee.work_item_types.seed import seed_project
from plane.tests.factories import ProjectMemberFactory

T = TypeKey
ADMIN = 20


@pytest.fixture
def project(workspace, create_user):
    p = Project.objects.create(name="P", identifier="P", workspace=workspace, created_by=create_user)
    ProjectMemberFactory(project=p, member=create_user, workspace=workspace, role=ADMIN)
    seed_project(p)
    return p


def _epic(project, name):
    return Issue.objects.create(name=name, project=project, type=get_type(project.workspace_id, T.EPIC))


def _attr(project, field_type, name=None):
    return Attribute.objects.create(
        project=project,
        issue_type=get_type(project.workspace_id, T.EPIC),
        name=name or f"custom {field_type}",
        field_type=field_type,
    )


def _val(issue, attribute, **cols):
    return AttributeValue.objects.create(issue=issue, attribute=attribute, project=issue.project, **cols)


def _list(client, workspace, project, **params):
    if "filters" in params:
        params["filters"] = json.dumps(params["filters"])
    return client.get(f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/", params)


def _ids(r):
    assert r.status_code == status.HTTP_200_OK, r.data
    return {str(i["id"]) for i in r.data["results"]}


@pytest.fixture
def a_b(project):
    return _epic(project, "A"), _epic(project, "B")


@pytest.mark.contract
@pytest.mark.django_db
def test_display_properties_accepts_attribute_key(session_client, workspace, project):
    attr = _attr(project, "text")
    key = f"attribute:{attr.id}"
    url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/user-properties/"
    r = session_client.patch(url, {"display_properties": {key: True, "priority": False}}, format="json")
    assert r.status_code == status.HTTP_200_OK, r.data
    assert session_client.get(url).data["display_properties"][key] is True
    assert ProjectUserProperty.objects.get(project=project).display_properties[key] is True


@pytest.mark.contract
@pytest.mark.django_db
def test_filter_text_contains(session_client, workspace, project, a_b):
    a, b = a_b
    attr = _attr(project, "text")
    _val(a, attr, value_text="Hello World")
    _val(b, attr, value_text="bye")
    r = _list(session_client, workspace, project, filters={f"attribute:{attr.id}__contains": "world"})
    assert _ids(r) == {str(a.id)}


@pytest.mark.contract
@pytest.mark.django_db
def test_filter_number_range(session_client, workspace, project, a_b):
    a, b = a_b
    attr = _attr(project, "number")
    _val(a, attr, value_number=Decimal(3))
    _val(b, attr, value_number=Decimal(13))
    r = _list(session_client, workspace, project, filters={f"attribute:{attr.id}__range": "1,5"})
    assert _ids(r) == {str(a.id)}


@pytest.mark.contract
@pytest.mark.django_db
def test_filter_date_range(session_client, workspace, project, a_b):
    a, b = a_b
    attr = _attr(project, "date")
    _val(a, attr, value_datetime=timezone.make_aware(dt.datetime(2026, 1, 10), dt.timezone.utc))
    _val(b, attr, value_datetime=timezone.make_aware(dt.datetime(2026, 3, 1), dt.timezone.utc))
    r = _list(session_client, workspace, project, filters={f"attribute:{attr.id}__range": "2026-01-01,2026-01-31"})
    assert _ids(r) == {str(a.id)}


@pytest.mark.contract
@pytest.mark.django_db
def test_filter_boolean_exact(session_client, workspace, project, a_b):
    a, b = a_b
    attr = _attr(project, "boolean")
    _val(a, attr, value_boolean=True)
    _val(b, attr, value_boolean=False)
    r = _list(session_client, workspace, project, filters={f"attribute:{attr.id}": "true"})
    assert _ids(r) == {str(a.id)}


@pytest.mark.contract
@pytest.mark.django_db
def test_filter_select_and_multi_select_in(session_client, workspace, project, a_b):
    a, b = a_b
    sel = _attr(project, "select")
    o1 = AttributeOption.objects.create(attribute=sel, name="o1")
    o2 = AttributeOption.objects.create(attribute=sel, name="o2")
    _val(a, sel, value_option=o1)
    _val(b, sel, value_option=o2)
    r = _list(session_client, workspace, project, filters={f"attribute:{sel.id}": str(o1.id)})
    assert _ids(r) == {str(a.id)}

    multi = _attr(project, "multi_select")
    m1 = AttributeOption.objects.create(attribute=multi, name="m1")
    m2 = AttributeOption.objects.create(attribute=multi, name="m2")
    _val(a, multi, value_option=m1)
    _val(a, multi, value_option=m2)
    _val(b, multi, value_option=m2)
    r = _list(session_client, workspace, project, filters={f"attribute:{multi.id}__in": [str(m1.id)]})
    assert _ids(r) == {str(a.id)}


@pytest.mark.contract
@pytest.mark.django_db
def test_filter_member(session_client, workspace, project, a_b, create_user):
    a, b = a_b
    attr = _attr(project, "member")
    _val(a, attr, value_uuid=create_user.id)
    r = _list(session_client, workspace, project, filters={f"attribute:{attr.id}__in": [str(create_user.id)]})
    assert _ids(r) == {str(a.id)}


@pytest.mark.contract
@pytest.mark.django_db
def test_filter_bad_operator_400_flat(session_client, workspace, project):
    attr = _attr(project, "text")
    r = _list(session_client, workspace, project, filters={f"attribute:{attr.id}__range": "1,2"})
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert set(r.data) == {"error_code", "message", "details"}, r.data


@pytest.mark.contract
@pytest.mark.django_db
def test_filter_attribute_of_other_project_400(session_client, workspace, project, create_user):
    other = Project.objects.create(name="O", identifier="O", workspace=workspace, created_by=create_user)
    seed_project(other)
    attr = _attr(other, "text")
    r = _list(session_client, workspace, project, filters={f"attribute:{attr.id}__contains": "x"})
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert r.data["error_code"] == "invalid_attribute"


@pytest.mark.contract
@pytest.mark.django_db
def test_filter_isnull_for_none_group(session_client, workspace, project, a_b):
    a, b = a_b
    sel = _attr(project, "select")
    _val(a, sel, value_option=AttributeOption.objects.create(attribute=sel, name="o1"))
    r = _list(session_client, workspace, project, filters={f"attribute:{sel.id}__isnull": "true"})
    assert _ids(r) == {str(b.id)}
    r = _list(session_client, workspace, project, filters={"type__isnull": "true"})
    assert _ids(r) == set()


@pytest.mark.contract
@pytest.mark.django_db
def test_filter_by_type(session_client, workspace, project, a_b):
    a, b = a_b
    feature = Issue.objects.create(name="F", project=project, type=get_type(workspace.id, T.FEATURE), parent=a)
    r = _list(session_client, workspace, project, filters={"type": "feature"})
    assert _ids(r) == {str(feature.id)}
    r = _list(session_client, workspace, project, filters={"type__in": [str(get_type(workspace.id, T.EPIC).id)]})
    assert _ids(r) == {str(a.id), str(b.id)}


@pytest.mark.contract
@pytest.mark.django_db
def test_group_by_type(session_client, workspace, project, a_b):
    a, b = a_b
    feature = Issue.objects.create(name="F", project=project, type=get_type(workspace.id, T.FEATURE), parent=a)
    r = _list(session_client, workspace, project, group_by="type")
    assert r.status_code == status.HTTP_200_OK, r.data
    groups = r.data["results"]
    epic_id, feature_id = str(get_type(workspace.id, T.EPIC).id), str(get_type(workspace.id, T.FEATURE).id)
    assert {str(i["id"]) for i in groups[epic_id]["results"]} == {str(a.id), str(b.id)}
    assert [str(i["id"]) for i in groups[feature_id]["results"]] == [str(feature.id)]


@pytest.mark.contract
@pytest.mark.django_db
def test_group_by_select_attribute(session_client, workspace, project, a_b):
    a, b = a_b
    sel = _attr(project, "select")
    o1 = AttributeOption.objects.create(attribute=sel, name="o1")
    _val(a, sel, value_option=o1)
    r = _list(session_client, workspace, project, group_by=f"attribute:{sel.id}")
    assert r.status_code == status.HTTP_200_OK, r.data
    groups = r.data["results"]
    assert [str(i["id"]) for i in groups[str(o1.id)]["results"]] == [str(a.id)]
    assert [str(i["id"]) for i in groups["None"]["results"]] == [str(b.id)]


@pytest.mark.contract
@pytest.mark.django_db
def test_group_by_boolean_attribute(session_client, workspace, project, a_b):
    a, b = a_b
    attr = _attr(project, "boolean")
    _val(a, attr, value_boolean=True)
    _val(b, attr, value_boolean=False)
    r = _list(session_client, workspace, project, group_by=f"attribute:{attr.id}")
    assert r.status_code == status.HTTP_200_OK, r.data
    groups = r.data["results"]
    assert [str(i["id"]) for i in groups["True"]["results"]] == [str(a.id)]
    assert [str(i["id"]) for i in groups["False"]["results"]] == [str(b.id)]


@pytest.mark.contract
@pytest.mark.django_db
def test_group_by_text_attribute_400(session_client, workspace, project):
    attr = _attr(project, "text")
    r = _list(session_client, workspace, project, group_by=f"attribute:{attr.id}")
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert set(r.data) == {"error_code", "message", "details"}, r.data
    assert r.data["error_code"] == "invalid_group_by"


@pytest.mark.contract
@pytest.mark.django_db
def test_existing_list_unchanged_without_new_keys(session_client, workspace, project, a_b):
    a, b = a_b
    r = _list(session_client, workspace, project, filters={"priority": "none"})
    assert _ids(r) == {str(a.id), str(b.id)}
    r = _list(session_client, workspace, project, group_by="priority")
    assert r.status_code == status.HTTP_200_OK
    assert {str(i["id"]) for i in r.data["results"]["none"]["results"]} == {str(a.id), str(b.id)}
    r = _list(session_client, workspace, project, filters={"nope": "x"})
    assert r.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.contract
@pytest.mark.django_db
def test_group_by_raw_attr_name_400_on_project_list(session_client, workspace, project, a_b):
    sel = _attr(project, "select")
    for raw in (f"attr_{sel.id.hex}", "ee_type"):
        r = _list(session_client, workspace, project, group_by=raw)
        assert r.status_code == status.HTTP_400_BAD_REQUEST, (raw, r.status_code)


@pytest.mark.contract
@pytest.mark.django_db
def test_group_by_raw_attr_name_400_on_cycle_list(session_client, workspace, project, create_user):
    sel = _attr(project, "select")
    cycle = Cycle.objects.create(name="C", project=project, workspace=workspace, owned_by=create_user)
    url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/cycles/{cycle.id}/cycle-issues/"
    for raw in (f"attr_{sel.id.hex}", f"attribute:{sel.id}", "type"):
        r = session_client.get(url, {"group_by": raw})
        assert r.status_code == status.HTTP_400_BAD_REQUEST, (raw, r.status_code)


@pytest.mark.contract
@pytest.mark.django_db
def test_ungrouped_list_row_has_type_id(session_client, workspace, project, a_b):
    a, _ = a_b
    r = _list(session_client, workspace, project)
    row = next(i for i in r.data["results"] if str(i["id"]) == str(a.id))
    assert str(row["type_id"]) == str(a.type_id)


@pytest.mark.contract
@pytest.mark.django_db
def test_list_without_ee_keys_touches_no_attribute_tables(session_client, workspace, project, a_b):
    for params in ({}, {"group_by": "priority"}, {"filters": {"priority": "none"}}):
        with CaptureQueriesContext(connection) as ctx:
            r = _list(session_client, workspace, project, **params)
        assert r.status_code == status.HTTP_200_OK
        assert not [q for q in ctx.captured_queries if '"attribute' in q["sql"]], params


@pytest.mark.contract
@pytest.mark.django_db
def test_sub_group_by_attribute(session_client, workspace, project, a_b):
    a, b = a_b
    attr = _attr(project, "boolean")
    _val(a, attr, value_boolean=True)
    r = _list(session_client, workspace, project, group_by="priority", sub_group_by=f"attribute:{attr.id}")
    assert r.status_code == status.HTTP_200_OK, r.data
    sub = r.data["results"]["none"]["results"]
    assert [str(i["id"]) for i in sub["True"]["results"]] == [str(a.id)]
    assert [str(i["id"]) for i in sub["None"]["results"]] == [str(b.id)]


@pytest.mark.contract
@pytest.mark.django_db
def test_filter_type_in_by_agile_key(session_client, workspace, project, a_b):
    a, b = a_b
    feature = Issue.objects.create(name="F", project=project, type=get_type(workspace.id, T.FEATURE), parent=a)
    r = _list(session_client, workspace, project, filters={"type__in": ["feature", "epic"]})
    assert _ids(r) == {str(a.id), str(b.id), str(feature.id)}


@pytest.mark.contract
@pytest.mark.django_db
def test_malformed_attribute_id_400(session_client, workspace, project):
    r = _list(session_client, workspace, project, filters={"attribute:not-a-uuid__contains": "x"})
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert r.data["error_code"] == "invalid_attribute"
    r = _list(session_client, workspace, project, group_by="attribute:not-a-uuid")
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert r.data["error_code"] == "invalid_attribute"


@pytest.mark.contract
@pytest.mark.django_db
def test_filter_boolean_in(session_client, workspace, project, a_b):
    a, b = a_b
    attr = _attr(project, "boolean")
    _val(a, attr, value_boolean=True)
    _val(b, attr, value_boolean=False)
    r = _list(session_client, workspace, project, filters={f"attribute:{attr.id}__in": ["true", "false"]})
    assert _ids(r) == {str(a.id), str(b.id)}


@pytest.mark.contract
@pytest.mark.django_db
def test_filter_number_date_gte_lte_and_text_icontains(session_client, workspace, project, a_b):
    a, b = a_b
    num, day, txt = _attr(project, "number"), _attr(project, "date"), _attr(project, "text")
    _val(a, num, value_number=Decimal(3))
    _val(b, num, value_number=Decimal(13))
    _val(a, day, value_datetime=timezone.make_aware(dt.datetime(2026, 1, 10), dt.timezone.utc))
    _val(b, day, value_datetime=timezone.make_aware(dt.datetime(2026, 3, 1), dt.timezone.utc))
    _val(a, txt, value_text="Hello World")
    _val(b, txt, value_text="bye")

    def ids(key, value):
        return _ids(_list(session_client, workspace, project, filters={key: value}))

    assert ids(f"attribute:{num.id}__gte", "5") == {str(b.id)}
    assert ids(f"attribute:{num.id}__lte", "3") == {str(a.id)}
    assert ids(f"attribute:{num.id}", "13") == {str(b.id)}
    assert ids(f"attribute:{day.id}__gte", "2026-02-01") == {str(b.id)}
    assert ids(f"attribute:{day.id}__lte", "2026-01-10") == {str(a.id)}
    assert ids(f"attribute:{day.id}", "2026-03-01") == {str(b.id)}
    assert ids(f"attribute:{txt.id}__icontains", "WORLD") == {str(a.id)}


@pytest.mark.contract
@pytest.mark.django_db
@pytest.mark.parametrize(
    "op,value",
    [("", "2026-02-30"), ("__gte", "2026-02-30"), ("__lte", "2026-13-01"), ("__range", "2026-01-01,2026-02-30")],
)
def test_filter_invalid_calendar_date_400(session_client, workspace, project, op, value):
    day = _attr(project, "date")
    r = _list(session_client, workspace, project, filters={f"attribute:{day.id}{op}": value})
    assert r.status_code == status.HTTP_400_BAD_REQUEST and r.data["error_code"] == "invalid_filter", r.data


@pytest.mark.contract
@pytest.mark.django_db
@pytest.mark.parametrize("op,value", [("", "NaN"), ("__gte", "Infinity"), ("__lte", "abc"), ("__range", "1,x")])
def test_filter_invalid_number_400(session_client, workspace, project, op, value):
    num = _attr(project, "number")
    r = _list(session_client, workspace, project, filters={f"attribute:{num.id}{op}": value})
    assert r.status_code == status.HTTP_400_BAD_REQUEST and r.data["error_code"] == "invalid_filter", r.data
