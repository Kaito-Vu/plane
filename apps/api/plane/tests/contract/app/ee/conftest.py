import pytest

from plane.db.models import Issue, Project, ProjectMember, State
from plane.ee.work_item_types.constants import TypeKey
from plane.ee.work_item_types.registry import get_type
from plane.ee.work_item_types.seed import seed_project


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(name="P", identifier="P", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    seed_project(project)
    return project


@pytest.fixture
def states(project):
    def mk(name, group, **kw):
        return State.objects.create(name=name, group=group, project=project, workspace=project.workspace, **kw)

    return {
        "todo": mk("Todo", "unstarted", default=True),
        "doing": mk("Doing", "started"),
        "done": mk("Done", "completed"),
        "cancelled": mk("Cancelled", "cancelled"),
    }


@pytest.fixture
def mk(workspace, project, states):
    """mk(type_key, parent=None, state="todo", **fields) -> Issue"""

    def make(key: TypeKey, parent=None, state="todo", **kw):
        return Issue.objects.create(
            name=key.value,
            project=project,
            type=get_type(workspace.id, key),
            parent=parent,
            state=states[state],
            **kw,
        )

    return make


@pytest.fixture
def story(mk):
    epic = mk(TypeKey.EPIC)
    return mk(TypeKey.USER_STORY, parent=mk(TypeKey.FEATURE, parent=epic))
