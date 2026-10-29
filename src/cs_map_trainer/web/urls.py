from django.contrib import admin
from django.urls import include, path

from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.account.urls")),
    path("accounts/social/", include("allauth.socialaccount.urls")),
    path("accounts/steam/login/", views.connect_steam, name="steam_login"),
    path("accounts/steam/login/callback/", views.connected_steam, name="steam_callback"),
    path("backend/history/", views.history),
    path("backend/uploads/", views.upload_start),
    path("backend/uploads/<uuid:upload_id>/complete/", views.upload_complete),
    path("backend/uploads/<uuid:upload_id>/", views.upload_detail),
    path("backend/uploads/<uuid:upload_id>/selection/", views.upload_selection),
    path("backend/uploads/<uuid:upload_id>/pack/", views.upload_pack),
    path(
        "backend/uploads/<uuid:upload_id>/scenarios/<str:scenario_id>/export/",
        views.upload_export,
    ),
    path("backend/account/delete/", views.account_delete),
]
