from __future__ import annotations

from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

from .api import api


def healthz(_request):
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/_allauth/", include("allauth.headless.urls")),
    path("api/", api.urls),
    path("healthz", healthz),
]
