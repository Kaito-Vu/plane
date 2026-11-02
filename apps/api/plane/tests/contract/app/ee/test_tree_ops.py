from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status

from plane.bgtasks.issue_automation_task import archive_old_issues
from plane.db.models import Issue
from plane.ee.work_item_types.constants import TypeKey
from plane.ee.work_item_types.tree_ops import restore_subtree, soft_delete_subtree, subtree_count

T = TypeKey


def _url(workspace, project, suffix=""):
    return f"/api/workspaces/{workspace.slug}/projects/{project.id}/{suffix}"


def _row(issue):
    return Issue.all_objects.get(pk=issue.pk)


@pytest.mark.contract
@pytest.mark.django_db
def test_delete_story_soft_deletes_whole_subtree_same_deleted_at(session_client, workspace, project, story, mk):
    task = mk(T.TASK, parent=story)
    sub = mk(T.SUB_TASK, parent=task)
    bug = mk(T.BUG, parent=story)
    assert subtree_count(story) == 3
    r = session_client.delete(_url(workspace, project, f"issues/{story.id}/"))
    assert r.status_code == status.HTTP_204_NO_CONTENT
    stamps = {_row(i).deleted_at for i in (story, task, sub, bug)}
    assert len(stamps) == 1 and None not in stamps


@pytest.mark.contract
@pytest.mark.django_db
def test_restore_parent_restores_only_same_batch(story, mk):
    early, late = mk(T.TASK, parent=story), mk(T.TASK, parent=story)
    assert soft_delete_subtree(early) == 1
    Issue.all_objects.filter(pk=early.pk).update(deleted_at=timezone.now() - timedelta(days=1))
    assert soft_delete_subtree(story) == 2
    assert restore_subtree(_row(story)) == 2
    assert _row(story).deleted_at is None and _row(late).deleted_at is None
    assert _row(early).deleted_at is not None


@pytest.mark.contract
@pytest.mark.django_db
def test_bulk_delete_cascades(session_client, workspace, project, story, mk):
    task = mk(T.TASK, parent=story)
    r = session_client.delete(
        _url(workspace, project, "bulk-delete-issues/"), {"issue_ids": [str(story.id)]}, format="json"
    )
    assert r.status_code == status.HTTP_200_OK
    assert _row(task).deleted_at is not None and _row(task).deleted_at == _row(story).deleted_at


@pytest.mark.contract
@pytest.mark.django_db
def test_archive_story_archives_tasks_and_bugs(session_client, workspace, project, story, mk):
    task = mk(T.TASK, parent=story, state="done")
    bug = mk(T.BUG, parent=task, state="cancelled")
    Issue.objects.filter(pk=story.pk).update(state=task.state)
    r = session_client.post(_url(workspace, project, f"issues/{story.id}/archive/"))
    assert r.status_code == status.HTTP_200_OK, r.data
    assert all(_row(i).archived_at for i in (story, task, bug))


@pytest.mark.contract
@pytest.mark.django_db
def test_bulk_archive_archives_subtree(session_client, workspace, project, story, mk):
    task = mk(T.TASK, parent=story, state="done")
    Issue.objects.filter(pk=story.pk).update(state=task.state)
    r = session_client.post(
        _url(workspace, project, "bulk-archive-issues/"), {"issue_ids": [str(story.id)]}, format="json"
    )
    assert r.status_code == status.HTTP_200_OK, r.data
    assert _row(task).archived_at is not None


@pytest.mark.contract
@pytest.mark.django_db
def test_auto_archive_skips_open_trees(project, story, mk, states):
    project.archive_in = 1
    project.save()
    open_story = mk(T.USER_STORY, parent=story.parent, state="done")
    mk(T.TASK, parent=open_story, state="doing")
    done_story = mk(T.USER_STORY, parent=story.parent, state="done")
    mk(T.TASK, parent=done_story, state="cancelled")
    Issue.objects.filter(project=project).update(updated_at=timezone.now() - timedelta(days=60))
    archive_old_issues()
    assert _row(open_story).archived_at is None
    assert _row(done_story).archived_at is not None


@pytest.mark.contract
@pytest.mark.django_db
def test_auto_archive_archives_candidate_subtree(project, story, mk, caplog):
    project.archive_in = 1
    project.save()
    done_story = mk(T.USER_STORY, parent=story.parent, state="done")
    fresh_task = mk(T.TASK, parent=done_story, state="done")
    open_story = mk(T.USER_STORY, parent=story.parent, state="done")
    mk(T.TASK, parent=open_story, state="doing")
    old = timezone.now() - timedelta(days=60)
    Issue.objects.filter(pk__in=[done_story.pk, open_story.pk]).update(updated_at=old)
    with caplog.at_level("INFO", logger="plane.worker"):
        archive_old_issues()
    # fresh_task is too recent to be a candidate itself, but goes with its archived parent
    assert _row(done_story).archived_at is not None and _row(fresh_task).archived_at is not None
    assert str(open_story.id) in caplog.text


def _archived_tree(session_client, workspace, project, story, mk):
    task = mk(T.TASK, parent=story, state="done")
    sub = mk(T.SUB_TASK, parent=task, state="done")
    Issue.objects.filter(pk=story.pk).update(state=task.state)
    r = session_client.post(_url(workspace, project, f"issues/{story.id}/archive/"))
    assert r.status_code == status.HTTP_200_OK, r.data
    return task, sub


@pytest.mark.contract
@pytest.mark.django_db
def test_unarchive_restores_same_cascade_only(session_client, workspace, project, story, mk):
    task, sub = _archived_tree(session_client, workspace, project, story, mk)
    other = mk(T.BUG, parent=story, state="done")
    Issue.all_objects.filter(pk=other.pk).update(archived_at=timezone.now().date() - timedelta(days=3))
    r = session_client.delete(_url(workspace, project, f"issues/{story.id}/archive/"))
    assert r.status_code == status.HTTP_204_NO_CONTENT, getattr(r, "data", None)
    assert _row(story).archived_at is None and _row(task).archived_at is None and _row(sub).archived_at is None
    assert _row(other).archived_at is not None


@pytest.mark.contract
@pytest.mark.django_db
def test_unarchive_under_archived_or_deleted_parent_400(session_client, workspace, project, story, mk):
    task, _ = _archived_tree(session_client, workspace, project, story, mk)
    r = session_client.delete(_url(workspace, project, f"issues/{task.id}/archive/"))
    assert r.status_code == status.HTTP_400_BAD_REQUEST and r.data["error_code"] == "parent_archived"
    Issue.all_objects.filter(pk=story.pk).update(archived_at=None, deleted_at=timezone.now())
    r = session_client.delete(_url(workspace, project, f"issues/{task.id}/archive/"))
    assert r.status_code == status.HTTP_400_BAD_REQUEST and r.data["error_code"] == "parent_deleted"
    assert _row(task).archived_at is not None


@pytest.mark.contract
@pytest.mark.django_db
def test_cascade_writes_descendant_activities(story, mk, create_user, django_capture_on_commit_callbacks):
    from unittest import mock

    task = mk(T.TASK, parent=story)
    sub = mk(T.SUB_TASK, parent=task)
    with mock.patch("plane.bgtasks.issue_activities_task.issue_activity.delay") as delay:
        with django_capture_on_commit_callbacks(execute=True):
            soft_delete_subtree(task, actor_id=create_user.id)
    calls = [c.kwargs for c in delay.call_args_list]
    assert [(c["type"], c["issue_id"]) for c in calls] == [("issue.activity.deleted", str(sub.id))]


@pytest.mark.contract
@pytest.mark.django_db
def test_archive_writes_descendant_activities(story, mk, create_user, django_capture_on_commit_callbacks):
    from unittest import mock

    from plane.ee.work_item_types.tree_ops import archive_subtree

    task = mk(T.TASK, parent=story, state="done")
    story.archived_at = timezone.now().date()
    with mock.patch("plane.bgtasks.issue_activities_task.issue_activity.delay") as delay:
        with django_capture_on_commit_callbacks(execute=True):
            archive_subtree(story, actor_id=create_user.id)
    (call,) = delay.call_args_list
    assert call.kwargs["issue_id"] == str(task.id) and "archived_at" in call.kwargs["requested_data"]


@pytest.mark.contract
@pytest.mark.django_db
def test_subtree_count_endpoint(session_client, workspace, project, story, mk):
    task = mk(T.TASK, parent=story)
    mk(T.SUB_TASK, parent=task)
    r = session_client.get(_url(workspace, project, f"issues/{story.id}/subtree-count/"))
    assert r.status_code == status.HTTP_200_OK and r.data == {"count": 2}
    r = session_client.get(_url(workspace, project, f"issues/{task.id}/subtree-count/"))
    assert r.data == {"count": 1}


@pytest.mark.contract
@pytest.mark.django_db
def test_subtree_count_for_archive_skips_archived(session_client, workspace, project, story, mk):
    mk(T.TASK, parent=story)
    old = mk(T.TASK, parent=story)
    Issue.all_objects.filter(pk=old.pk).update(archived_at=timezone.now().date())
    url = _url(workspace, project, f"issues/{story.id}/subtree-count/")
    assert session_client.get(url).data == {"count": 2}
    assert session_client.get(url + "?for=archive").data == {"count": 1}


@pytest.mark.contract
@pytest.mark.django_db
def test_subtree_count_restricted_guest_404(workspace, project, story):
    from rest_framework.test import APIClient

    from plane.tests.factories import ProjectMemberFactory, UserFactory, WorkspaceMemberFactory

    project.guest_view_all_features = False
    project.save()
    guest = UserFactory()
    WorkspaceMemberFactory(workspace=workspace, member=guest, role=5)
    ProjectMemberFactory(project=project, member=guest, workspace=workspace, role=5)
    c = APIClient()
    c.force_authenticate(user=guest)
    r = c.get(_url(workspace, project, f"issues/{story.id}/subtree-count/"))
    assert r.status_code == status.HTTP_404_NOT_FOUND
