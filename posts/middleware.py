import logging

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect

logger = logging.getLogger("worldlink.security")


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def _admin_url_path():
    p = getattr(settings, "ADMIN_URL_PATH", "admin").strip("/")
    return "/" + p + "/"


class RateLimitMiddleware:
    GENERAL_LIMIT = 120
    LOGIN_LIMIT = 30
    SIGNUP_LIMIT = 10
    WINDOW = 60

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip = _client_ip(request)
        path = request.path
        admin_path = _admin_url_path()

        if path.startswith(admin_path):
            return self.get_response(request)

        key = f"rl:{ip}:gen"
        count = cache.get(key, 0)
        if count >= self.GENERAL_LIMIT:
            logger.warning(f"RateLimit EXCEEDED (general) ip={ip} path={path}")
            return HttpResponse("طلبات كثيرة جدًا. حاول بعد قليل.", status=429)
        cache.set(key, count + 1, self.WINDOW)

        if path == "/login/" and request.method == "POST":
            key = f"rl:{ip}:login"
            count = cache.get(key, 0)
            if count >= self.LOGIN_LIMIT:
                logger.warning(f"RateLimit EXCEEDED (login) ip={ip}")
                return HttpResponse("محاولات دخول كثيرة. حاول بعد دقيقة.", status=429)
            cache.set(key, count + 1, self.WINDOW)

        if path == "/signup/" and request.method == "POST":
            key = f"rl:{ip}:signup"
            count = cache.get(key, 0)
            if count >= self.SIGNUP_LIMIT:
                logger.warning(f"RateLimit EXCEEDED (signup) ip={ip}")
                return HttpResponse("محاولات تسجيل كثيرة. حاول بعد دقيقة.", status=429)
            cache.set(key, count + 1, self.WINDOW)

        return self.get_response(request)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Permissions-Policy"] = (
            "geolocation=(), microphone=(self), camera=(self)"
        )
        response["Cross-Origin-Opener-Policy"] = "same-origin"
        response["X-Permitted-Cross-Domain-Policies"] = "none"
        return response


class SuspiciousActivityMiddleware:
    BLOCKED_PATHS = (
        ".env", ".git", "wp-admin", "wp-login", "phpmyadmin",
        "config.php", ".aws", ".ssh", "xmlrpc.php",
    )
    BAD_AGENTS = ("sqlmap", "nikto", "nmap", "acunetix", "masscan")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip = _client_ip(request)
        path = request.path.lower()
        ua = request.META.get("HTTP_USER_AGENT", "").lower()
        admin_path = _admin_url_path()

        if not request.path.startswith(admin_path):
            for blocked in self.BLOCKED_PATHS:
                if blocked in path:
                    logger.warning(f"BLOCKED PATH: ip={ip} path={request.path}")
                    return HttpResponseForbidden("ممنوع")
            for bad in self.BAD_AGENTS:
                if bad in ua:
                    logger.warning(f"SUSPICIOUS UA: ip={ip} ua={ua[:120]}")
                    return HttpResponseForbidden("ممنوع")

        return self.get_response(request)


class AdminSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        admin_path = _admin_url_path()
        if not request.path.startswith(admin_path):
            return self.get_response(request)

        ip = _client_ip(request)
        allowed_ips = getattr(settings, "ADMIN_ALLOWED_IPS", [])
        if allowed_ips and ip not in allowed_ips:
            logger.warning(f"ADMIN IP BLOCKED: ip={ip} path={request.path}")
            self._log(request, "access_denied", f"IP غير مسموح: {ip}")
            return HttpResponseForbidden(
                "🚫 الوصول مرفوض. عنوان IP غير مسموح."
            )

        if request.user.is_authenticated and request.user.is_staff:
            profile = getattr(request.user, "profile", None)
            if profile and not profile.is_2fa_enabled:
                logger.warning(f"ADMIN 2FA REQUIRED: user={request.user.username} ip={ip}")
                messages.error(request, "🛡️ للوصول إلى لوحة الإدارة، يجب تفعيل 2FA أولًا.")
                return redirect("security_settings")

        return self.get_response(request)

    def _log(self, request, action, details=""):
        try:
            from .models import AdminLog
            AdminLog.objects.create(
                user=request.user if request.user.is_authenticated else None,
                action=action,
                details=details[:500],
                ip_address=_client_ip(request),
                user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:300],
                path=request.path[:300],
            )
        except Exception:
            pass


class SessionTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            from .signals_security import set_current_request
            set_current_request(request)
        except Exception:
            pass

        response = self.get_response(request)

        if request.user.is_authenticated and request.session.session_key:
            try:
                self._track_session(request)
            except Exception as e:
                logger.warning(f"Session tracking error: {e}")

        return response

    def _track_session(self, request):
        from .models import UserSession
        from .security_utils import parse_user_agent

        session_key = request.session.session_key
        ip = _client_ip(request)
        ua = request.META.get("HTTP_USER_AGENT", "")
        device, browser, os_name = parse_user_agent(ua)

        obj, created = UserSession.objects.update_or_create(
            user=request.user,
            session_key=session_key,
            defaults={
                "ip_address": ip,
                "user_agent": ua[:1000],
                "device_type": device,
                "browser": browser,
                "os": os_name,
            },
        )

        UserSession.objects.filter(user=request.user).exclude(
            session_key=session_key
        ).update(is_current=False)
        UserSession.objects.filter(
            user=request.user, session_key=session_key
        ).update(is_current=True)

        from django.utils import timezone
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(days=90)
        UserSession.objects.filter(user=request.user, last_activity__lt=cutoff).delete()