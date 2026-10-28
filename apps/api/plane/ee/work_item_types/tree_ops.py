from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from plane.bgtasks.deletion_task import soft_delete_related_objects
from plane.db.models import Issue

from .constants import MAX_DEPTH

DONE_GROUPS = ("completed", "cancelled")


def _descendant_ids(root_ids, **filters) -> list:
    """All descendants (not the roots) matching filters, walking parent links level by level."""
    found, level = [], list(root_ids)
    for _ in range(MAX_DEPTH + 1):
        level = list(Issue.all_objects.filter(parent_id__in=level, **filters).values_list("id", flat=True))
        if not level:
            break
        found += level
    return found


def subtree_count(issue: Issue) -> int:
    """Live descendants that a delete/archive of issue would take with it (for the confirm dialog)."""
    return len(_descendant_ids([issue.id], deleted_at__isnull=True))


def soft_delete_subtree(issue: Issue) -> int:
    """Synchronously soft-delete issue + every live descendant with one shared deleted_at."""
    ids = [issue.id, *_descendant_ids([issue.id], deleted_at__isnull=True)]
    now = timezone.now()
    with transaction.atomic():
        count = Issue.all_objects.filter(id__in=ids, deleted_at__isnull=True).update(deleted_at=now)
        for pk in ids:  # cycle/module links etc. follow core's per-issue cascade
            transaction.on_commit(lambda pk=pk: soft_delete_related_objects.delay("db", "issue", pk))
    issue.deleted_at = now
    return count


def restore_subtree(issue: Issue) -> int:
    """Restore issue and only the descendants deleted in the same batch (same deleted_at)."""
    stamp = issue.deleted_at
    if stamp is None:
        return 0
    ids = [issue.id, *_descendant_ids([issue.id], deleted_at=stamp)]
    count = Issue.all_objects.filter(id__in=ids, deleted_at=stamp).update(deleted_at=None)
    issue.deleted_at = None
    return count


def archive_subtree(issue: Issue) -> int:
    """Archive every live, unarchived descendant with the root's archive date (root saved by the caller)."""
    archived_at = issue.archived_at or timezone.now().date()
    ids = _descendant_ids([issue.id], deleted_at__isnull=True)
    return Issue.all_objects.filter(id__in=ids, archived_at__isnull=True).update(archived_at=archived_at)


def auto_archive_candidates(qs: QuerySet) -> QuerySet:
    """Drop issues that still have a descendant outside Completed/Cancelled (auto-archive/close skip them)."""
    rows = list(
        Issue.all_objects.filter(project_id__in=qs.values("project_id"), deleted_at__isnull=True).values_list(
            "id", "parent_id", "state__group"
        )
    )
    parent_of = {i: p for i, p, _ in rows}
    blocked = set()
    for _, parent, group in rows:
        if group in DONE_GROUPS:
            continue
        hops = 0
        while parent is not None and parent not in blocked and hops <= MAX_DEPTH:
            blocked.add(parent)
            parent, hops = parent_of.get(parent), hops + 1
    return qs.exclude(id__in=blocked)
