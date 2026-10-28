import pytest

from plane.db.models import Issue, Project
from plane.ee.work_item_types.constants import TypeKey
from plane.ee.work_item_types.exceptions import WorkItemValidationError
from plane.ee.work_item_types.registry import get_type
from plane.ee.work_item_types.seed import seed_project
from plane.ee.work_item_types.validators import validate_work_item

T = TypeKey


def _project(workspace, user, ident="P"):
    project = Project.objects.create(name=ident, identifier=ident, workspace=workspace, created_by=user)
    seed_project(project)
    return project


def _code(**kwargs):
    with pytest.raises(WorkItemValidationError) as e:
        validate_work_item(attribute_values=None, **kwargs)
    return e.value.error_code


@pytest.mark.unit
@pytest.mark.django_db
def test_missing_type_rejected(workspace, create_user):
    project = _project(workspace, create_user)
    assert _code(project=project, issue_type_id=None, parent_id=None) == "type_required"


@pytest.mark.unit
@pytest.mark.django_db
def test_parent_rules(workspace, create_user):
    project = _project(workspace, create_user)
    validate_work_item(
        project=project, issue_type_id=get_type(workspace.id, T.EPIC).id, parent_id=None, attribute_values=None
    )
    task_id = get_type(workspace.id, T.TASK).id
    assert _code(project=project, issue_type_id=task_id, parent_id=None) == "parent_required"
    validate_work_item(project=project, issue_type_id=task_id, parent_id=None, attribute_values=None, triage=True)


@pytest.mark.unit
@pytest.mark.django_db
def test_type_immutable(workspace, create_user):
    project = _project(workspace, create_user)
    epic = Issue.objects.create(name="E", project=project, type=get_type(workspace.id, T.EPIC))
    feature_id = get_type(workspace.id, T.FEATURE).id
    assert _code(project=project, issue_type_id=feature_id, parent_id=None, instance=epic) == "type_immutable"


@pytest.mark.unit
@pytest.mark.django_db
def test_parent_other_project_rejected(workspace, create_user):
    project = _project(workspace, create_user)
    other = _project(workspace, create_user, "Q")
    epic = Issue.objects.create(name="E", project=other, type=get_type(workspace.id, T.EPIC))
    feature_id = get_type(workspace.id, T.FEATURE).id
    assert _code(project=project, issue_type_id=feature_id, parent_id=epic.id) == "parent_invalid"
