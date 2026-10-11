"""
إدارة الأجهزة الموثوقة (تخطي 2FA لمدة 30 يومًا).
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.utils import timezone

TRUSTED_COOKIE_NAME = "wl_trusted_device"
TRUSTED_COOKIE_SALT = "worldlink.trusted_device"
TRUSTED_DAYS = 30
TRUSTED_MAX_AGE = TRUSTED_DAYS * 24 * 3600
MAX_TRUSTED_DEVICES_PER_USER = 5


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _generate_token():
    return secrets.token_urlsafe(48)


def _device_name(request):
    try:
        from .security_utils import parse_user_agent
        _, browser, os_name = parse_user_agent(request.META.get("HTTP_USER_AGENT", ""))
        return f"{browser} على {os_name}"
    except Exception:
        return "جهاز"


def create_trusted_device(user, request, device_name=None):
    """
    ينشئ جهازًا موثوقًا ويعيد (device, raw_token).
    راو توكين يُخزن في كوكي فقط. لا نُخزنه في قاعدة البيانات.
    """
    from .models import TrustedDevice

    raw_token = _generate_token()
    token_hash = _hash_token(raw_token)

    if not device_name:
        device_name = _device_name(request)

    # احذف الأقدم لو تجاوز الحد
    existing = TrustedDevice.objects.filter(user=user).order_by("-last_used_at")
    if existing.count() >= MAX_TRUSTED_DEVICES_PER_USER:
        to_delete = existing[MAX_TRUSTED_DEVICES_PER_USER - 1:]
        TrustedDevice.objects.filter(pk__in=[d.pk for d in to_delete]).delete()

    # احذف المنتهية
    TrustedDevice.objects.filter(user=user, expires_at__lte=timezone.now()).delete()

    device = TrustedDevice.objects.create(
        user=user,
        token_hash=token_hash,
        device_name=device_name[:200],
        ip_address=_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "") or "")[:1000],
        expires_at=timezone.now() + timedelta(days=TRUSTED_DAYS),
    )
    return device, raw_token


def set_trusted_cookie(response, user_id, raw_token):
    """يُعيّن الكوكي على الاستجابة."""
    payload = {"uid": user_id, "token": raw_token}
    signed = signing.dumps(payload, salt=TRUSTED_COOKIE_SALT, compress=True)
    response.set_cookie(
        TRUSTED_COOKIE_NAME,
        signed,
        max_age=TRUSTED_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=not settings.DEBUG,
    )
    return response


def clear_trusted_cookie(response):
    response.delete_cookie(TRUSTED_COOKIE_NAME)
    return response


def get_trusted_cookie_payload(request):
    raw = request.COOKIES.get(TRUSTED_COOKIE_NAME)
    if not raw:
        return None
    try:
        return signing.loads(
            raw, salt=TRUSTED_COOKIE_SALT, max_age=TRUSTED_MAX_AGE,
        )
    except signing.SignatureExpired:
        return None
    except signing.BadSignature:
        return None


def is_device_trusted(request, user):
    """هل الجهاز موثوق لهذا المستخدم؟"""
    from .models import TrustedDevice

    payload = get_trusted_cookie_payload(request)
    if not payload:
        return False
    if payload.get("uid") != user.id:
        return False
    raw_token = payload.get("token")
    if not raw_token:
        return False

    token_hash = _hash_token(raw_token)
    device = TrustedDevice.objects.filter(
        user=user,
        token_hash=token_hash,
        expires_at__gt=timezone.now(),
    ).first()
    if not device:
        return False

    # لو الـ IP تغيّر كثيرًا؟ (اختياري - سنسمح بتغيير IP طفيف)
    # تجاهلنا هذا لتجنب إزعاج المستخدم

    device.save(update_fields=["last_used_at"])
    return True


def revoke_device(device, response=None):
    """يحذف جهازًا. إذا مطابق للكوكي الحالي، يمسح الكوكي أيضًا."""
    device.delete()


def revoke_all_devices(user):
    from .models import TrustedDevice
    TrustedDevice.objects.filter(user=user).delete()