from django.contrib import admin
from django.urls import include, path

from . import billing_views, pages, views

urlpatterns = [
    path("", pages.home, name="home"),
    path("account/", pages.account, name="account"),
    path("account/billing/checkout/", pages.billing_checkout, name="billing_checkout"),
    path("account/billing/portal/", pages.billing_portal, name="billing_portal"),
    path("account/billing/refresh/", pages.billing_refresh, name="billing_refresh"),
    path("account/billing/return/", pages.billing_return, name="billing_return"),
    path("billing/stripe/webhook/", billing_views.stripe_webhook, name="stripe_webhook"),
    path("account/delete/", pages.remove_account, name="remove_account"),
    path("history/", pages.history, name="history"),
    path("uploads/<uuid:upload_id>/", pages.report, name="report"),
    path("uploads/<uuid:upload_id>/selection/", pages.selection, name="selection"),
    path("uploads/<uuid:upload_id>/delete/", pages.remove_upload, name="remove_upload"),
    path("uploads/<uuid:upload_id>/training/", pages.training, name="training"),
    path(
        "uploads/<uuid:upload_id>/scenarios/<str:scenario_id>/review/",
        pages.review,
        name="review",
    ),
    path("practice/", pages.practice, name="practice"),
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
