from plane.db.models import IssueType, Project, Workspace
from plane.db.models.issue_type import ProjectIssueType

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


def seed_workspace(workspace: Workspace) -> list[IssueType]:
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
    for issue_type in seed_workspace(project.workspace):
        ProjectIssueType.objects.get_or_create(
            project=project,
            issue_type=issue_type,
            defaults={"workspace_id": project.workspace_id, "level": int(issue_type.level)},
        )
