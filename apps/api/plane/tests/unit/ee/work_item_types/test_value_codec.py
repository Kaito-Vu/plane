import datetime as dt
import uuid
from decimal import Decimal

import pytest

from plane.db.models import Issue, IssueType, Project
from plane.ee.models import Attribute, AttributeOption, AttributeValue
from plane.ee.work_item_types.exceptions import WorkItemValidationError
from plane.ee.work_item_types.seed import seed_project
from plane.ee.work_item_types.value_codec import coerce_value, missing_required, write_values

UID = str(uuid.uuid4())

COLUMN = {
    "text": "value_text",
    "textarea": "value_text",
    "url": "value_text",
    "number": "value_number",
    "boolean": "value_boolean",
    "date": "value_datetime",
    "datetime": "value_datetime",
    "select": "value_option",
    "multi_select": "value_option",
    "member": "value_uuid",
    "multi_member": "value_uuid",
}
EXPECTED = {
    "text": "hi",
    "textarea": "<p>hi</p>",
    "url": "https://example.com/x",
    "number": Decimal(3),
    "boolean": True,
    "date": dt.datetime(2026, 1, 2, tzinfo=dt.timezone.utc),
    "datetime": dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.timezone.utc),
    "member": uuid.UUID(UID),
    "multi_member": [uuid.UUID(UID)],
}


@pytest.fixture
def project(workspace, create_user):
    p = Project.objects.create(name="P", identifier="P", workspace=workspace, created_by=create_user)
    seed_project(p)
    return p


def _attr(project, field_type, type_key="bug", **kw):
    bug = IssueType.objects.get(workspace=project.workspace, external_id=type_key)
    attr = Attribute.objects.create(
        project=project, issue_type=bug, name=f"a-{field_type}-{uuid.uuid4().hex[:6]}", field_type=field_type, **kw
    )
    if field_type in ("select", "multi_select"):
        AttributeOption.objects.create(attribute=attr, name="x")
    return attr


def _opt(attr):
    return str(attr.options.first().id)


GOOD = {
    "text": "hi",
    "textarea": "<p>hi</p>",
    "number": 3,
    "boolean": True,
    "date": "2026-01-02",
    "datetime": "2026-01-02T03:04:05Z",
    "url": "https://example.com/x",
    "member": UID,
    "multi_member": [UID],
}
BAD = {
    "text": 5,
    "textarea": ["x"],
    "number": "abc",
    "boolean": "yes",
    "date": "nope",
    "datetime": "nope",
    "url": "not a url",
    "member": "nope",
    "multi_member": "nope",
}


@pytest.mark.unit
@pytest.mark.django_db
@pytest.mark.parametrize("ft", sorted(GOOD) + ["select", "multi_select"])
def test_valid_value_per_field_type(project, ft):
    attr = _attr(project, ft)
    raw = {"select": lambda: _opt(attr), "multi_select": lambda: [_opt(attr)]}.get(ft, lambda: GOOD[ft])()
    out = coerce_value(attr, raw)
    col = COLUMN[ft]
    assert list(out) == [col]
    if ft == "select":
        assert out[col] == attr.options.first()
    elif ft == "multi_select":
        assert out[col] == [attr.options.first()]
    else:
        assert out[col] == EXPECTED[ft]


@pytest.mark.unit
@pytest.mark.django_db
@pytest.mark.parametrize("ft", sorted(BAD) + ["select", "multi_select"])
def test_invalid_value_per_field_type(project, ft):
    attr = _attr(project, ft)
    raw = {"select": "nope", "multi_select": ["nope"]}.get(ft) or BAD[ft]
    with pytest.raises(WorkItemValidationError) as exc:
        coerce_value(attr, raw)
    assert exc.value.error_code == "invalid_value"
    assert exc.value.detail["details"]["attribute_id"] == str(attr.id)


@pytest.mark.unit
@pytest.mark.django_db
def test_negative_story_points_rejected(project):
    sp = Attribute.objects.get(project=project, system_key="story_points", issue_type__external_id="bug")
    with pytest.raises(WorkItemValidationError):
        coerce_value(sp, -1)
    assert coerce_value(sp, 0)


@pytest.mark.unit
@pytest.mark.django_db
def test_option_of_other_attribute_rejected(project):
    a, b = _attr(project, "select"), _attr(project, "select")
    with pytest.raises(WorkItemValidationError):
        coerce_value(a, _opt(b))


@pytest.mark.unit
@pytest.mark.django_db
def test_missing_required_lists_bug_fields(project):
    bug = IssueType.objects.get(workspace=project.workspace, external_id="bug")
    req = set(Attribute.objects.filter(project=project, issue_type=bug, is_required=True).values_list("id", flat=True))
    assert len(req) == 3
    assert set(missing_required(project.id, bug.id, {})) == req
    one = next(iter(req))
    assert set(missing_required(project.id, bug.id, {one: "x"})) == req - {one}


@pytest.mark.unit
@pytest.mark.django_db
def test_write_values_upserts_and_rewrites_multi(project, workspace, create_user):
    bug = IssueType.objects.get(workspace=workspace, external_id="epic")
    issue = Issue.objects.create(name="i", project=project, workspace=workspace, type=bug, created_by=create_user)
    ms = _attr(project, "multi_select", "epic")
    other = AttributeOption.objects.create(attribute=ms, name="y")
    num = _attr(project, "number", "epic")
    write_values(issue, {ms.id: [_opt(ms), str(other.id)], num.id: 2}, project=project)
    write_values(issue, {ms.id: [str(other.id)], num.id: 5}, project=project)
    assert AttributeValue.objects.filter(issue=issue, attribute=ms).count() == 1
    assert AttributeValue.objects.get(issue=issue, attribute=num).value_number == 5


@pytest.mark.unit
@pytest.mark.django_db
@pytest.mark.parametrize(
    "ft,raw", [("date", "2026-13-45"), ("datetime", "2026-13-45T25:00:00"), ("date", "2026-02-30")]
)
def test_malformed_date_is_invalid_value(project, ft, raw):
    with pytest.raises(WorkItemValidationError) as exc:
        coerce_value(_attr(project, ft), raw)
    assert exc.value.error_code == "invalid_value"


@pytest.mark.unit
@pytest.mark.django_db
@pytest.mark.parametrize("raw", [True, False, "1.00001", 10**16, "NaN", "Infinity", -0.5])
def test_number_rejects(project, raw):
    with pytest.raises(WorkItemValidationError):
        coerce_value(_attr(project, "number"), raw)


@pytest.mark.unit
@pytest.mark.django_db
def test_number_accepts_limits_and_business_value_integer(project):
    attr = _attr(project, "number")
    assert coerce_value(attr, "9999999999999999.9999")["value_number"] == Decimal("9999999999999999.9999")
    bv = Attribute.objects.get(project=project, system_key="business_value", issue_type__external_id="epic")
    assert coerce_value(bv, 5)["value_number"] == 5
    with pytest.raises(WorkItemValidationError):
        coerce_value(bv, 5.5)


@pytest.mark.unit
@pytest.mark.django_db
def test_empty_input_returns_empty(project):
    attr = _attr(project, "text")
    for raw in (None, "", [], ()):
        assert coerce_value(attr, raw) == {}


@pytest.mark.unit
@pytest.mark.django_db
def test_inactive_option_rejected(project):
    attr = _attr(project, "select")
    attr.options.update(is_active=False)
    with pytest.raises(WorkItemValidationError):
        coerce_value(attr, _opt(attr))


def _epic_issue(project, workspace, create_user):
    epic = IssueType.objects.get(workspace=workspace, external_id="epic")
    return Issue.objects.create(name="i", project=project, workspace=workspace, type=epic, created_by=create_user)


@pytest.mark.unit
@pytest.mark.django_db
def test_write_values_clears_and_rolls_back(project, workspace, create_user):
    issue = _epic_issue(project, workspace, create_user)
    a, b = _attr(project, "number", "epic"), _attr(project, "text", "epic")
    write_values(issue, {a.id: 2}, project=project)
    write_values(issue, {a.id: None}, project=project)
    assert not AttributeValue.objects.filter(issue=issue, attribute=a).exists()
    write_values(issue, {a.id: 2}, project=project)
    with pytest.raises(WorkItemValidationError):
        write_values(issue, {a.id: 9, b.id: 123}, project=project)
    assert AttributeValue.objects.get(issue=issue, attribute=a).value_number == 2


@pytest.mark.unit
@pytest.mark.django_db
def test_write_values_bad_keys(project, workspace, create_user):
    issue = _epic_issue(project, workspace, create_user)
    for key in ("not-a-uuid", uuid.uuid4()):
        with pytest.raises(WorkItemValidationError):
            write_values(issue, {key: 1}, project=project)
