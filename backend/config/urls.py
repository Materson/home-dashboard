from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
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

if settings.DEBUG:
    # In production nginx serves /static/ directly — this route only activates
    # when running `manage.py runserver` locally.
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
