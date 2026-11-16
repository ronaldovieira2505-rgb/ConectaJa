from django.conf import settings
from django.contrib import admin
from django.http import FileResponse, Http404
from django.urls import include, path, re_path
from django.views.decorators.cache import never_cache


@never_cache
def spa_index(request):
    """Entrega o index.html do React para as rotas do frontend (deploy sem Vite)."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        raise Http404
    return FileResponse(index.open("rb"), content_type="text/html")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    re_path(r"^(?!api/|admin/|static/).*$", spa_index),
]
