import pytest
from rest_framework import status

from plane.db.models import Cycle, CycleIssue, Issue
from plane.ee.models import Attribute, AttributeValue
from plane.ee.work_item_types.constants import TypeKey
from plane.ee.work_item_types.registry import get_type

T = TypeKey


def _url(workspace, project, suffix=""):
    return f"/api/workspaces/{workspace.slug}/projects/{project.id}/{suffix}"


def _flat(r, code):
    assert r.status_code == status.HTTP_400_BAD_REQUEST, r.data
    assert set(r.data) == {"error_code", "message", "details"}, r.data
    assert r.data["error_code"] == code


@pytest.fixture
def cycles(project, create_user):
    def mk(name):
        return Cycle.objects.create(name=name, project=project, workspace=project.workspace, owned_by=create_user)

    return mk("A"), mk("B")


def _add_to_cycle(client, workspace, project, cycle, *issues):
    return client.post(
        _url(workspace, project, f"cycles/{cycle.id}/cycle-issues/"),
        {"issues": [str(i.id) for i in issues]},
        format="json",
    )


@pytest.mark.contract
@pytest.mark.django_db
def test_epic_cannot_join_cycle(session_client, workspace, project, story, cycles):
    epic = story.parent.parent
    r = _add_to_cycle(session_client, workspace, project, cycles[0], epic)
    _flat(r, "cycle_type_not_allowed")
    assert not CycleIssue.objects.filter(issue=epic).exists()


@pytest.mark.contract
@pytest.mark.django_db
def test_task_cycle_mismatch_returns_warning_not_error(session_client, workspace, project, story, mk, cycles):
    task = mk(T.TASK, parent=story)
    assert _add_to_cycle(session_client, workspace, project, cycles[0], story).status_code == 201
    r = _add_to_cycle(session_client, workspace, project, cycles[1], task)
    assert r.status_code == status.HTTP_201_CREATED, r.data
    assert r.data["warnings"] and str(task.id) in r.data["warnings"][0]
    assert CycleIssue.objects.filter(issue=task, cycle=cycles[1]).exists()
    # same cycle as the story: no warning
    r = _add_to_cycle(session_client, workspace, project, cycles[0], task)
    assert r.status_code == 201 and not r.data.get("warnings")


@pytest.mark.contract
@pytest.mark.django_db
def test_cannot_complete_story_with_open_task(session_client, workspace, project, story, mk, states):
    task = mk(T.TASK, parent=story)
    mk(T.TASK, parent=story, state="done")
    r = session_client.patch(
        _url(workspace, project, f"issues/{story.id}/"), {"state_id": str(states["done"].id)}, format="json"
    )
    _flat(r, "open_children")
    assert [str(c) for c in r.data["details"]["children"]] == [str(task.id)]
    assert Issue.objects.get(pk=story.pk).state_id == states["todo"].id


@pytest.mark.contract
@pytest.mark.django_db
def test_complete_allowed_when_children_cancelled(session_client, workspace, project, story, mk, states):
    mk(T.TASK, parent=story, state="cancelled")
    mk(T.TASK, parent=story, state="done")
    r = session_client.patch(
        _url(workspace, project, f"issues/{story.id}/"), {"state_id": str(states["done"].id)}, format="json"
    )
    assert r.status_code == status.HTTP_204_NO_CONTENT, r.data


@pytest.mark.contract
@pytest.mark.django_db
def test_reparent_reruns_validation(session_client, workspace, project, story, mk):
    task = mk(T.TASK, parent=story)
    epic = story.parent.parent
    r = session_client.patch(_url(workspace, project, f"issues/{task.id}/"), {"parent_id": str(epic.id)}, format="json")
    _flat(r, "parent_type_invalid")
    # sub-issue bulk re-parent goes through the same gate
    r = session_client.post(
        _url(workspace, project, f"issues/{epic.id}/sub-issues/"), {"sub_issue_ids": [str(task.id)]}, format="json"
    )
    _flat(r, "parent_type_invalid")
    assert Issue.objects.get(pk=task.pk).parent_id == story.id


@pytest.mark.contract
@pytest.mark.django_db
def test_duplicate_keeps_type_parent_values(session_client, workspace, project, story):
    """The web 'Make a copy' re-posts type, parent and attribute values; the copy keeps all three."""
    ac = Attribute.objects.get(
        project=project, issue_type=get_type(workspace.id, T.USER_STORY), system_key="acceptance_criteria"
    )
    body = {
        "name": "copy",
        "type_id": str(story.type_id),
        "parent_id": str(story.parent_id),
        "attribute_values": {str(ac.id): "Given"},
    }
    r = session_client.post(_url(workspace, project, "issues/"), body, format="json")
    assert r.status_code == status.HTTP_201_CREATED, r.data
    copy = Issue.objects.get(pk=r.data["id"])
    assert (copy.type_id, copy.parent_id) == (story.type_id, story.parent_id)
    assert AttributeValue.objects.get(issue=copy, attribute=ac).value_text == "Given"


@pytest.mark.contract
@pytest.mark.django_db
def test_draft_incomplete_ok_but_convert_validates(session_client, workspace, project):
    task_type = str(get_type(workspace.id, T.TASK).id)
    r = session_client.post(
        f"/api/workspaces/{workspace.slug}/draft-issues/",
        {"name": "d", "project_id": str(project.id), "type_id": task_type},
        format="json",
    )
    assert r.status_code == status.HTTP_201_CREATED, r.data
    r2 = session_client.post(
        f"/api/workspaces/{workspace.slug}/draft-to-issue/{r.data['id']}/",
        {"name": "d", "type_id": task_type},
        format="json",
    )
    assert r2.status_code == status.HTTP_400_BAD_REQUEST
    assert "parent_required" in str(r2.data)


@pytest.mark.contract
@pytest.mark.django_db
def test_backlog_order_uses_sort_order_not_priority(session_client, workspace, project, story, mk):
    low_ranked_first = mk(T.TASK, parent=story, priority="low", sort_order=1000)
    urgent_second = mk(T.TASK, parent=story, priority="urgent", sort_order=2000)
    ids = f"{low_ranked_first.id},{urgent_second.id}"
    r = session_client.get(_url(workspace, project, f"issues/list/?issues={ids}&order_by=sort_order"))
    assert r.status_code == status.HTTP_200_OK, r.data
    assert [str(row["id"]) for row in r.data] == [str(low_ranked_first.id), str(urgent_second.id)]


@pytest.mark.contract
@pytest.mark.django_db
def test_draft_convert_epic_into_cycle_rejected(session_client, workspace, project, cycles):
    epic_type = str(get_type(workspace.id, T.EPIC).id)
    r = session_client.post(
        f"/api/workspaces/{workspace.slug}/draft-issues/",
        {"name": "d", "project_id": str(project.id), "type_id": epic_type},
        format="json",
    )
    r2 = session_client.post(
        f"/api/workspaces/{workspace.slug}/draft-to-issue/{r.data['id']}/",
        {"name": "d", "type_id": epic_type, "cycle_id": str(cycles[0].id)},
        format="json",
    )
    _flat(r2, "cycle_type_not_allowed")
    assert not Issue.objects.filter(name="d").exists()
