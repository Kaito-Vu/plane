from django.urls import path

from .views.attributes import (
    AttributeApplyTemplateEndpoint,
    AttributeDetailEndpoint,
    AttributeListEndpoint,
    AttributeOptionDetailEndpoint,
    AttributeOptionListEndpoint,
    AttributeReorderEndpoint,
)
from .views.templates import (
    AttributeTemplateDetailEndpoint,
    AttributeTemplateListEndpoint,
    AttributeTemplateOptionDetailEndpoint,
    AttributeTemplateOptionEndpoint,
    AttributeTemplateReorderEndpoint,
)

W = "workspaces/<str:slug>/"
P = W + "projects/<uuid:project_id>/attributes/"

urlpatterns = [
    path(W + "attribute-templates/", AttributeTemplateListEndpoint.as_view()),
    path(W + "attribute-templates/reorder/", AttributeTemplateReorderEndpoint.as_view()),
    path(W + "attribute-templates/<uuid:pk>/", AttributeTemplateDetailEndpoint.as_view()),
    path(W + "attribute-templates/<uuid:pk>/options/", AttributeTemplateOptionEndpoint.as_view()),
    path(
        W + "attribute-templates/<uuid:pk>/options/<uuid:option_id>/", AttributeTemplateOptionDetailEndpoint.as_view()
    ),
    path(P, AttributeListEndpoint.as_view()),
    path(P + "reorder/", AttributeReorderEndpoint.as_view()),
    path(P + "apply-template/", AttributeApplyTemplateEndpoint.as_view()),
    path(P + "<uuid:pk>/", AttributeDetailEndpoint.as_view()),
    path(P + "<uuid:pk>/options/", AttributeOptionListEndpoint.as_view()),
    path(P + "<uuid:pk>/options/<uuid:option_id>/", AttributeOptionDetailEndpoint.as_view()),
]
