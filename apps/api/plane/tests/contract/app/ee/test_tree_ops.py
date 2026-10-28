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
