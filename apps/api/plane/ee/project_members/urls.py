from django.urls import path

from .views import EeProjectMemberViewSet

# Same routes/names as plane/app/urls/project.py; plane.ee.urls is included first so these win.
_base = "workspaces/<str:slug>/projects/<uuid:project_id>/members/"

urlpatterns = [
    path(_base, EeProjectMemberViewSet.as_view({"get": "list", "post": "create"}), name="project-member"),
    path(
        _base + "<uuid:pk>/",
        EeProjectMemberViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="project-member",
    ),
    path(_base + "leave/", EeProjectMemberViewSet.as_view({"post": "leave"}), name="project-member"),
]
