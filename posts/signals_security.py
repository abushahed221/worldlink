"""
إشارات لكشف الحسابات المزيفة تلقائيًا.
تُستدعى عند إنشاء مستخدم جديد.
"""
import logging

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger("worldlink.security")


def _ip_from_request(request):
    if not request:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# تخزين آخر طلب في سياق thread-local
try:
    from asgiref.local import Local
    _local = Local()
except ImportError:
    _local = None


def set_current_request(request):
    if _local is not None:
        _local.request = request


def get_current_request():
    if _local is not None:
        return getattr(_local, "request", None)
    return None


@receiver(post_save, sender=User)
def check_new_user(sender, instance, created, **kwargs):
    """يفحص كل مستخدم جديد فورًا."""
    if not created:
        return

    from .security_utils import (
        is_disposable_email, is_suspicious_username,
        check_rapid_signups, check_ip_multi_accounts,
    )
    from .models import SuspiciousAccount

    signals = []
    score = 0

    # 1. الاسم مشبوه
    if is_suspicious_username(instance.username):
        signals.append("اسم مستخدم مشبوه")
        score += 2

    # 2. البريد مؤقت
    if is_disposable_email(instance.email):
        signals.append("بريد مؤقت")
        score += 3

    # 3. التسجيلات السريعة من نفس IP
    request = get_current_request()
    ip = _ip_from_request(request) if request else None

    if ip:
        if check_rapid_signups(ip):
            signals.append(f"عدة تسجيلات من نفس IP ({ip}) في وقت قصير")
            score += 3
        multi = check_ip_multi_accounts(ip)
        if multi >= 3:
            signals.append(f"{multi} حسابات من نفس IP")
            score += 2

    # 4. البريد يشبه الاسم (fake pattern)
    if instance.email and instance.username.lower() in instance.email.lower():
        pass  # عادي

    # 5. البريد ليس بريدًا حقيقيًا
    if not instance.email or "@" not in instance.email:
        signals.append("بريد غير صحيح")
        score += 1

    if score == 0:
        return

    level = "low"
    if score >= 6:
        level = "critical"
    elif score >= 4:
        level = "high"
    elif score >= 2:
        level = "medium"

    import json
    SuspiciousAccount.objects.create(
        user=instance,
        level=level,
        reason="; ".join(signals),
        signals=json.dumps(signals, ensure_ascii=False),
        ip_address=ip,
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:500] if request else ""),
    )

    logger.warning(
        f"SUSPICIOUS ACCOUNT: user={instance.username} "
        f"level={level} signals={signals} ip={ip}"
    )

    # حظر فوري لو المستوى حرج
    if level == "critical":
        try:
            profile = instance.profile
            profile.is_verified = False
            profile.save(update_fields=["is_verified"])
            logger.warning(f"AUTO-UNVERIFIED: {instance.username} (critical)")
        except Exception:
            pass