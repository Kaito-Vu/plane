from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.db.models.issue_type import ProjectIssueType

from ..constants import AGILE_SOURCE, TypeKey

ORDER = {k.value: i for i, k in enumerate(TypeKey)}


class ProjectTypesEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id):
        rows = ProjectIssueType.objects.filter(
            project_id=project_id,
            project__workspace__slug=slug,
            issue_type__external_source=AGILE_SOURCE,
        ).select_related("issue_type")
        data = [
            {
                "id": t.id,
                "key": t.external_id,
                "name": t.name,
                "level": t.level,
                "is_epic": t.is_epic,
            }
            for t in (r.issue_type for r in rows)
            if t.external_id in ORDER
        ]
        return Response(sorted(data, key=lambda d: ORDER[d["key"]]))
