"""
تسجيل كل أنشطة الأدمن.
"""
from django.contrib.admin.models import LogEntry
from django.contrib.auth.signals import (
    user_logged_in, user_logged_out, user_login_failed,
)
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import AdminLog


def _client_ip(request):
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _user_agent(request):
    if request is None:
        return ""
    return (request.META.get("HTTP_USER_AGENT") or "")[:300]


def _is_admin_request(request):
    """هل الطلب داخل لوحة الأدمن؟"""
    if request is None:
        return False
    from django.conf import settings
    admin_path = getattr(settings, "ADMIN_URL_PATH", "admin")
    admin_url = "/" + admin_path.strip("/") + "/"
    return request.path.startswith(admin_url)


@receiver(user_logged_in)
def log_admin_login(sender, request, user, **kwargs):
    if not _is_admin_request(request):
        return
    AdminLog.objects.create(
        user=user,
        action="login_success",
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
        path=request.path,
        details=f"دخول أدمن: {user.username}",
    )


@receiver(user_login_failed)
def log_admin_login_failed(sender, credentials, request=None, **kwargs):
    if not _is_admin_request(request):
        return
    username = (credentials or {}).get("username", "")
    AdminLog.objects.create(
        user=None,
        username_tried=username[:150],
        action="login_fail",
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
        path=request.path if request else "",
        details=f"محاولة دخول فاشلة: {username}",
    )


@receiver(user_logged_out)
def log_admin_logout(sender, request, user, **kwargs):
    if user is None:
        return
    if not _is_admin_request(request):
        return
    AdminLog.objects.create(
        user=user,
        action="logout",
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
        path=request.path if request else "",
        details=f"خروج: {user.username}",
    )


# تسجيل كل إجراء يقوم به الأدمن على النماذج
@receiver(post_save, sender=LogEntry)
def log_admin_action(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        user = instance.user
    except Exception:
        user = None
    AdminLog.objects.create(
        user=user,
        action={
            1: "create", 2: "update", 3: "delete",
        }.get(instance.action_flag, "other"),
        target_model=instance.content_type.model if instance.content_type else "",
        target_id=str(instance.object_id or ""),
        details=(instance.change_message or "")[:500],
        path="",
    )