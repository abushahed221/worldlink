import os

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

# مسار الأدمن المخفي
_admin_path = os.environ.get("ADMIN_URL_PATH", "admin").strip("/")

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    path(f"{_admin_path}/", admin.site.urls),
    path("", include("posts.urls")),
]

# إعادة تسمية عنوان لوحة الإدارة في المتصفح
admin.site.site_header = "لوحة إدارة WorldLink"
admin.site.site_title = "WorldLink Admin"
admin.site.index_title = "مرحبًا بك في لوحة الإدارة"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)