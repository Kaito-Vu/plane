from django.db import connection, transaction

from plane.db.models import IssueType, Project, Workspace
from plane.db.models.issue_type import ProjectIssueType
from plane.ee.models import Attribute, AttributeOption
from plane.utils.uuid import convert_uuid_to_integer

from .attribute_catalog import ATTRIBUTE_CATALOG
from .constants import AGILE_SOURCE, TypeKey

T = TypeKey

# key -> (name, level)
SEED_TYPES: dict[TypeKey, tuple[str, int]] = {
    T.EPIC: ("Epic", 4),
    T.FEATURE: ("Feature", 3),
    T.USER_STORY: ("User Story", 2),
    T.TASK: ("Task", 1),
    T.BUG: ("Bug", 1),
    T.SUB_TASK: ("Sub-task", 0),
}


def _lock_workspace(workspace_id) -> None:
    # IssueType has no unique constraint (no core migration), so concurrent seeds are serialized
    # with a transaction-level advisory lock, same pattern as Issue.save.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [convert_uuid_to_integer(workspace_id)])


def seed_workspace(workspace: Workspace) -> list[IssueType]:
    with transaction.atomic():
        _lock_workspace(workspace.id)
        types = []
        for key, (name, level) in SEED_TYPES.items():
            issue_type, _ = IssueType.objects.get_or_create(
                workspace=workspace,
                external_source=AGILE_SOURCE,
                external_id=key.value,
                defaults={"name": name, "level": level, "is_epic": key == T.EPIC},
            )
            types.append(issue_type)
        return types


def seed_project(project: Project) -> None:
    with transaction.atomic():
        for issue_type in seed_workspace(project.workspace):  # holds the workspace lock until commit
            ProjectIssueType.objects.get_or_create(
                project=project,
                issue_type=issue_type,
                defaults={"workspace_id": project.workspace_id, "level": int(issue_type.level)},
            )
            _seed_attributes(project, issue_type)


def _seed_attributes(project: Project, issue_type: IssueType) -> None:
    for order, spec in enumerate(ATTRIBUTE_CATALOG[TypeKey(issue_type.external_id)], start=1):
        attr, created = Attribute.objects.get_or_create(
            project=project,
            issue_type=issue_type,
            is_system=True,
            system_key=spec.system_key,
            defaults={
                "workspace_id": project.workspace_id,
                "name": spec.name,
                "field_type": spec.field_type,
                "is_required": spec.is_required,
                "sort_order": order * 10000,
            },
        )
        if created:
            for i, name in enumerate(spec.options, start=1):
                AttributeOption.objects.create(attribute=attr, name=name, sort_order=i * 10000)
