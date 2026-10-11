import logging
import re
from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone

logger = logging.getLogger("worldlink.security")


DISPOSABLE_DOMAINS = {
    "tempmail.com", "10minutemail.com", "guerrillamail.com",
    "mailinator.com", "throwawaymail.com", "yopmail.com",
    "temp-mail.org", "getnada.com", "sharklasers.com",
    "trashmail.com", "fakeinbox.com", "mytemp.email",
}


def is_disposable_email(email):
    if not email or "@" not in email:
        return True
    domain = email.split("@")[1].lower()
    return domain in DISPOSABLE_DOMAINS


def is_suspicious_username(username):
    if not username:
        return True
    if len(username) < 3:
        return True
    if username.isdigit():
        return True
    if not re.search(r"[a-zA-Z\u0600-\u06FF]", username):
        return True
    if re.search(r"\d{5,}", username):
        return True
    reserved = {
        "admin", "administrator", "root", "system", "moderator",
        "support", "help", "worldlink", "official", "staff",
    }
    if username.lower() in reserved:
        return True
    return False


def looks_like_bot(request):
    ua = request.META.get("HTTP_USER_AGENT", "")
    al = request.META.get("HTTP_ACCEPT_LANGUAGE", "")
    if not ua or len(ua) < 10:
        return True
    suspicious_tokens = ["bot", "spider", "crawler", "scraper", "phantom", "selenium"]
    ua_lower = ua.lower()
    if any(t in ua_lower for t in suspicious_tokens):
        if "google" in ua_lower or "bing" in ua_lower or "yandex" in ua_lower:
            return False
        return True
    if not al:
        return True
    return False


def check_rapid_signups(ip, window_minutes=10, threshold=3):
    """هل تم تسجيل أكثر من X حساب من نفس IP في آخر Y دقيقة؟"""
    if not ip:
        return False
    from .models import LoginAttempt
    since = timezone.now() - timedelta(minutes=window_minutes)
    count = LoginAttempt.objects.filter(
        ip_address=ip,
        created_at__gte=since,
    ).count()
    return count >= threshold


def check_ip_multi_accounts(ip):
    """كم حساب يستخدم نفس IP؟ (تقريبي عبر LoginAttempt)"""
    if not ip:
        return 0
    from .models import LoginAttempt
    return LoginAttempt.objects.filter(
        ip_address=ip, success=True,
    ).values("username").distinct().count()


def parse_user_agent(ua_string):
    """استخراج بسيط: نوع الجهاز، المتصفح، نظام التشغيل."""
    ua = (ua_string or "").lower()
    device = "كمبيوتر"
    if "mobile" in ua or "android" in ua or "iphone" in ua:
        device = "جوال"
    elif "tablet" in ua or "ipad" in ua:
        device = "تابلت"

    browser = "غير معروف"
    for token, name in [
        ("edg", "Edge"),
        ("chrome", "Chrome"),
        ("firefox", "Firefox"),
        ("safari", "Safari"),
        ("opera", "Opera"),
        ("msie", "Internet Explorer"),
        ("trident", "Internet Explorer"),
    ]:
        if token in ua:
            browser = name
            break

    os_name = "غير معروف"
    for token, name in [
        ("windows nt 10", "Windows 10/11"),
        ("windows nt 6.3", "Windows 8.1"),
        ("windows nt 6.1", "Windows 7"),
        ("mac os x", "macOS"),
        ("android", "Android"),
        ("iphone", "iOS"),
        ("ipad", "iPadOS"),
        ("linux", "Linux"),
    ]:
        if token in ua:
            os_name = name
            break

    return device, browser, os_name