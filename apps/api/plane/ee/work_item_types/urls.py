from django.urls import path

from .views.attributes import (
    AttributeApplyTemplateEndpoint,
    AttributeDetailEndpoint,
    AttributeListEndpoint,
    AttributeOptionDetailEndpoint,
    AttributeOptionListEndpoint,
    AttributeReorderEndpoint,
)
from .views.bulk_tree import BulkTreeEndpoint
from .views.imports import (
    ImportBatchEndpoint,
    ImportCommitEndpoint,
    ImportRowDetailEndpoint,
    ImportRowsEndpoint,
    ImportValidateEndpoint,
)
from .views.templates import (
    AttributeTemplateDetailEndpoint,
    AttributeTemplateListEndpoint,
    AttributeTemplateOptionDetailEndpoint,
    AttributeTemplateOptionEndpoint,
    AttributeTemplateReorderEndpoint,
)
from .views.types import ProjectTypesEndpoint
from .views.values import (
    IssueAttributeValuesEndpoint,
    IssueSubtreeCountEndpoint,
    ProjectAttributeValuesEndpoint,
)

W = "workspaces/<str:slug>/"
I = W + "projects/<uuid:project_id>/imports/"  # noqa: E741
P = W + "projects/<uuid:project_id>/attributes/"

urlpatterns = [
    path(W + "attribute-templates/", AttributeTemplateListEndpoint.as_view()),
    path(W + "attribute-templates/reorder/", AttributeTemplateReorderEndpoint.as_view()),
    path(W + "attribute-templates/<uuid:pk>/", AttributeTemplateDetailEndpoint.as_view()),
    path(W + "attribute-templates/<uuid:pk>/options/", AttributeTemplateOptionEndpoint.as_view()),
    path(
        W + "attribute-templates/<uuid:pk>/options/<uuid:option_id>/", AttributeTemplateOptionDetailEndpoint.as_view()
    ),
    path(
        W + "projects/<uuid:project_id>/issues/<uuid:issue_id>/attribute-values/",
        IssueAttributeValuesEndpoint.as_view(),
    ),
    path(
        W + "projects/<uuid:project_id>/issues/<uuid:issue_id>/subtree-count/",
        IssueSubtreeCountEndpoint.as_view(),
    ),
    path(W + "projects/<uuid:project_id>/attribute-values/", ProjectAttributeValuesEndpoint.as_view()),
    path(W + "projects/<uuid:project_id>/issues/bulk-tree/", BulkTreeEndpoint.as_view()),
    path(I, ImportBatchEndpoint.as_view()),
    path(I + "<uuid:pk>/rows/", ImportRowsEndpoint.as_view()),
    path(I + "<uuid:pk>/rows/<uuid:row_id>/", ImportRowDetailEndpoint.as_view()),
    path(I + "<uuid:pk>/validate/", ImportValidateEndpoint.as_view()),
    path(I + "<uuid:pk>/commit/", ImportCommitEndpoint.as_view()),
    path(W + "projects/<uuid:project_id>/work-item-types/", ProjectTypesEndpoint.as_view(), name="ee-work-item-types"),
    path(P, AttributeListEndpoint.as_view()),
    path(P + "reorder/", AttributeReorderEndpoint.as_view()),
    path(P + "apply-template/", AttributeApplyTemplateEndpoint.as_view()),
    path(P + "<uuid:pk>/", AttributeDetailEndpoint.as_view()),
    path(P + "<uuid:pk>/options/", AttributeOptionListEndpoint.as_view()),
    path(P + "<uuid:pk>/options/<uuid:option_id>/", AttributeOptionDetailEndpoint.as_view()),
]
