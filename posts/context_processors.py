def notifications(request):
    if request.user.is_authenticated:
        unread = request.user.notifications.filter(is_read=False).count()
        return {
            "unread_notifications": unread,
            "requires_2fa": getattr(request.user.profile, "is_2fa_enabled", False),
        }
    return {"unread_notifications": 0, "requires_2fa": False}