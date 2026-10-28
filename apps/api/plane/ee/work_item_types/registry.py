from uuid import UUID

from plane.db.models import IssueType

from .constants import AGILE_SOURCE, TypeKey


def type_key_of(issue_type: IssueType | None) -> TypeKey | None:
    if issue_type is None or issue_type.external_source != AGILE_SOURCE:
        return None
    try:
        return TypeKey(issue_type.external_id)
    except ValueError:
        return None


def get_type(workspace_id: UUID, key: TypeKey) -> IssueType:
    return IssueType.objects.get(workspace_id=workspace_id, external_source=AGILE_SOURCE, external_id=key.value)
