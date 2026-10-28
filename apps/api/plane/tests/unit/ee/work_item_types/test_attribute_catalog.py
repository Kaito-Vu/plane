import pytest

from plane.db.models import Project
from plane.ee.models import Attribute
from plane.ee.work_item_types.attribute_catalog import ATTRIBUTE_CATALOG
from plane.ee.work_item_types.constants import TypeKey as T
from plane.ee.work_item_types.seed import seed_project

BIG = ["Acceptance Criteria", "Story Points", "Business Value", "Time Criticality", "Value Area", "Project Phase"]
HOURS = ["Original Estimate", "Remaining Work", "Spent Time"]
SPEC = {
    T.EPIC: (BIG, set()),
    T.FEATURE: (BIG, set()),
    T.USER_STORY: (BIG, {"Acceptance Criteria"}),
    T.TASK: (["Acceptance Criteria", *HOURS], set()),
    T.SUB_TASK: (HOURS, set()),
    T.BUG: (
        ["Severity", "Steps to Reproduce", "Expected Result", "Actual Result", "System Info", "Version Found"]
        + ["Story Points"],
        {"Severity", "Steps to Reproduce", "Actual Result"},
    ),
}


@pytest.mark.unit
def test_system_attributes_match_spec_table():
    assert set(ATTRIBUTE_CATALOG) == set(T)
    for key, (names, required) in SPEC.items():
        specs = ATTRIBUTE_CATALOG[key]
        assert [s.name for s in specs] == names
        assert {s.name for s in specs if s.is_required} == required


@pytest.mark.unit
def test_catalog_options():
    by_key = {s.system_key: s for s in ATTRIBUTE_CATALOG[T.BUG]}
    assert by_key["severity"].options == ("Critical", "Major", "Minor", "Trivial")
    epic = {s.system_key: s for s in ATTRIBUTE_CATALOG[T.EPIC]}
    assert epic["project_phase"].options == ("Initiation", "Planning", "Execution", "Closing")
    assert epic["value_area"].options == ("Business", "Architectural")
    assert epic["acceptance_criteria"].field_type == "textarea"


@pytest.mark.unit
@pytest.mark.django_db
def test_seed_project_creates_system_attributes_idempotently(workspace, create_user):
    project = Project.objects.create(name="P", identifier="P", workspace=workspace, created_by=create_user)
    seed_project(project)
    seed_project(project)
    expected = sum(len(v) for v in ATTRIBUTE_CATALOG.values())
    assert Attribute.objects.filter(project=project, is_system=True).count() == expected
    sev = Attribute.objects.get(project=project, system_key="severity")
    assert sev.options.count() == 4 and sev.is_required
