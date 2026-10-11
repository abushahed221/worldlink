from datetime import timedelta

from django.contrib import admin, messages
from django.utils import timezone

from .models import (
    Profile, Post, PostImage, Comment, Notification, Friendship, UserRelation,
    LoginAttempt, Bookmark, HiddenPost, Report, Conversation, Message,
    Group, GroupMember, GroupPost, Page, PageFollower, PagePost,
    AdminLog, UserSession, SuspiciousAccount, TrustedDevice,
)


class PostImageInline(admin.TabularInline):
    model = PostImage
    extra = 1


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user", "location", "birthdate", "job_title",
        "is_verified", "is_2fa_enabled", "is_suspended", "created_at",
    )
    search_fields = ("user__username", "user__email", "bio", "job_title", "workplace")
    list_filter = ("is_verified", "is_2fa_enabled", "is_suspended", "gender")
    readonly_fields = ("totp_secret", "backup_codes", "last_2fa_verified")
    actions = [
        "suspend_7_days", "suspend_30_days", "suspend_permanent",
        "unsuspend", "warn_user", "reset_2fa",
    ]

    def suspend_7_days(self, request, queryset):
        until = timezone.now() + timedelta(days=7)
        for p in queryset:
            p.suspended_until = until
            p.suspension_reason = "مخالفة (7 أيام)."
            p.is_suspended = False
            p.save()
        self.message_user(request, "تم تعليق 7 أيام.", messages.WARNING)
    suspend_7_days.short_description = "⏸️ تعليق 7 أيام"

    def suspend_30_days(self, request, queryset):
        until = timezone.now() + timedelta(days=30)
        for p in queryset:
            p.suspended_until = until
            p.suspension_reason = "مخالفة متكررة (30 يومًا)."
            p.is_suspended = False
            p.save()
        self.message_user(request, "تم تعليق 30 يومًا.", messages.WARNING)
    suspend_30_days.short_description = "⏸️ تعليق 30 يومًا"

    def suspend_permanent(self, request, queryset):
        for p in queryset:
            p.is_suspended = True
            p.suspension_reason = "حظر دائم."
            p.save()
        self.message_user(request, "تم الحظر الدائم.", messages.ERROR)
    suspend_permanent.short_description = "⛔ حظر دائم"

    def unsuspend(self, request, queryset):
        queryset.update(is_suspended=False, suspended_until=None, suspension_reason="")
        self.message_user(request, "تم رفع الحظر.")
    unsuspend.short_description = "✅ رفع الحظر"

    def warn_user(self, request, queryset):
        for p in queryset:
            p.warning_count += 1
            p.save()
        self.message_user(request, "تم إرسال الإنذارات.", messages.WARNING)
    warn_user.short_description = "⚠️ إنذار"

    def reset_2fa(self, request, queryset):
        queryset.update(is_2fa_enabled=False, totp_secret="", backup_codes="")
        TrustedDevice.objects.filter(user__in=[p.user for p in queryset]).delete()
        self.message_user(request, "تم إعادة تعيين 2FA وحذف الأجهزة الموثوقة.", messages.WARNING)
    reset_2fa.short_description = "🔓 إعادة تعيين 2FA"


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("author", "short_content", "created_at", "is_hidden_by_admin")
    list_filter = ("created_at", "is_hidden_by_admin")
    search_fields = ("content", "author__username")
    inlines = [PostImageInline]
    actions = ["hide_posts", "unhide_posts", "delete_posts"]

    def short_content(self, obj):
        return obj.content[:50]
    short_content.short_description = "المحتوى"

    def hide_posts(self, request, queryset):
        queryset.update(is_hidden_by_admin=True, hidden_reason="مخالفة")
        self.message_user(request, "تم الحجب.")
    hide_posts.short_description = "🚫 حجب"

    def unhide_posts(self, request, queryset):
        queryset.update(is_hidden_by_admin=False, hidden_reason="")
        self.message_user(request, "تم إلغاء الحجب.")
    unhide_posts.short_description = "✅ إلغاء الحجب"

    def delete_posts(self, request, queryset):
        queryset.delete()
        self.message_user(request, "تم الحذف.")
    delete_posts.short_description = "🗑️ حذف"


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("author", "post", "parent", "created_at")
    search_fields = ("content", "author__username")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "sender", "notification_type", "is_read", "created_at")
    list_filter = ("notification_type", "is_read")


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ("from_user", "to_user", "status", "created_at")
    list_filter = ("status",)


@admin.register(UserRelation)
class UserRelationAdmin(admin.ModelAdmin):
    list_display = ("user", "target", "relation_type", "created_at")
    list_filter = ("relation_type",)


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("username", "ip_address", "success", "created_at")
    list_filter = ("success",)


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ("user", "post", "created_at")


@admin.register(HiddenPost)
class HiddenPostAdmin(admin.ModelAdmin):
    list_display = ("user", "post", "created_at")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("reporter", "post", "reported_user", "message", "reason", "is_reviewed", "created_at")
    list_filter = ("reason", "is_reviewed")
    actions = ["mark_reviewed"]

    def mark_reviewed(self, request, queryset):
        queryset.update(is_reviewed=True)
    mark_reviewed.short_description = "✅ مُراجَع"


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "mode", "disappear_after", "short_participants", "updated_at")
    list_filter = ("mode",)
    filter_horizontal = ("participants",)

    def short_participants(self, obj):
        return ", ".join(p.username for p in obj.participants.all())
    short_participants.short_description = "المشاركون"


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("sender", "conversation", "message_type", "is_read", "is_deleted", "created_at")
    list_filter = ("message_type", "is_read", "is_deleted")


class GroupMemberInline(admin.TabularInline):
    model = GroupMember
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "creator", "privacy", "created_at")
    list_filter = ("privacy", "is_hidden_by_admin")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [GroupMemberInline]


@admin.register(GroupMember)
class GroupMemberAdmin(admin.ModelAdmin):
    list_display = ("group", "user", "role", "joined_at")
    list_filter = ("role",)
    autocomplete_fields = ("user",)


@admin.register(GroupPost)
class GroupPostAdmin(admin.ModelAdmin):
    list_display = ("group", "author", "created_at")
    list_filter = ("group",)


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "category", "created_at")
    list_filter = ("category", "is_hidden_by_admin")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(PageFollower)
class PageFollowerAdmin(admin.ModelAdmin):
    list_display = ("page", "user", "followed_at")
    autocomplete_fields = ("user",)


@admin.register(PagePost)
class PagePostAdmin(admin.ModelAdmin):
    list_display = ("page", "author", "created_at")
    list_filter = ("page",)


# ==================== سجل الأدمن ====================
@admin.register(AdminLog)
class AdminLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "username_tried", "action", "ip_address")
    list_filter = ("action", "created_at")
    search_fields = ("user__username", "username_tried", "details", "ip_address")
    readonly_fields = (
        "user", "username_tried", "action", "target_model",
        "target_id", "details", "ip_address", "user_agent", "path", "created_at",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    actions = ["purge_old"]

    def purge_old(self, request, queryset):
        cutoff = timezone.now() - timedelta(days=90)
        deleted, _ = AdminLog.objects.filter(created_at__lt=cutoff).delete()
        self.message_user(request, f"تم حذف {deleted} سجل قديم.")
    purge_old.short_description = "🗑️ حذف السجلات الأقدم من 90 يومًا"


# ==================== الجلسات النشطة ====================
@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = (
        "user", "ip_address", "device_type", "browser", "os",
        "is_current", "last_activity",
    )
    list_filter = ("device_type", "browser", "os", "is_current")
    search_fields = ("user__username", "ip_address", "user_agent")
    readonly_fields = (
        "user", "session_key", "ip_address", "user_agent",
        "device_type", "browser", "os", "last_activity", "created_at",
    )
    date_hierarchy = "last_activity"

    def has_add_permission(self, request):
        return False

    actions = ["purge_old", "force_logout"]

    def purge_old(self, request, queryset):
        cutoff = timezone.now() - timedelta(days=90)
        deleted, _ = UserSession.objects.filter(last_activity__lt=cutoff).delete()
        self.message_user(request, f"تم حذف {deleted} جلسة قديمة.")
    purge_old.short_description = "🗑️ حذف الجلسات الأقدم من 90 يومًا"

    def force_logout(self, request, queryset):
        from django.contrib.sessions.models import Session
        count = 0
        for us in queryset:
            try:
                Session.objects.filter(session_key=us.session_key).delete()
                count += 1
            except Exception:
                pass
        queryset.delete()
        self.message_user(request, f"تم إنهاء {count} جلسة.", messages.WARNING)
    force_logout.short_description = "🚪 إنهاء الجلسات المحددة"


# ==================== الحسابات المشبوهة ====================
@admin.register(SuspiciousAccount)
class SuspiciousAccountAdmin(admin.ModelAdmin):
    list_display = (
        "user", "level", "status", "short_reason",
        "ip_address", "created_at",
    )
    list_filter = ("level", "status", "created_at")
    search_fields = ("user__username", "reason", "ip_address")
    readonly_fields = ("user", "reason", "signals", "ip_address", "user_agent", "created_at")
    date_hierarchy = "created_at"
    actions = ["mark_cleared", "mark_blocked", "suspend_user"]

    def short_reason(self, obj):
        return obj.reason[:60]
    short_reason.short_description = "السبب"

    def mark_cleared(self, request, queryset):
        queryset.update(
            status="cleared", reviewed_by=request.user, reviewed_at=timezone.now(),
        )
        self.message_user(request, "تم تحديدها كمُتحقق منها.")
    mark_cleared.short_description = "✅ تم التحقق (سليم)"

    def mark_blocked(self, request, queryset):
        queryset.update(
            status="blocked", reviewed_by=request.user, reviewed_at=timezone.now(),
        )
        self.message_user(request, "تم تحديدها كمحظورة.", messages.WARNING)
    mark_blocked.short_description = "⛔ حظر"

    def suspend_user(self, request, queryset):
        count = 0
        for flag in queryset:
            try:
                p = flag.user.profile
                p.is_suspended = True
                p.suspension_reason = "حساب مشبوه — مراجعة إدارية."
                p.save()
                count += 1
            except Exception:
                pass
        self.message_user(request, f"تم تعليق {count} حساب.", messages.ERROR)
    suspend_user.short_description = "⛔ تعليق الحساب نهائيًا"


# ==================== الأجهزة الموثوقة ====================
@admin.register(TrustedDevice)
class TrustedDeviceAdmin(admin.ModelAdmin):
    list_display = (
        "user", "device_name", "ip_address",
        "expires_at", "last_used_at", "created_at",
    )
    list_filter = ("created_at", "expires_at")
    search_fields = ("user__username", "device_name", "ip_address")
    readonly_fields = (
        "user", "token_hash", "device_name", "ip_address",
        "user_agent", "expires_at", "last_used_at", "created_at",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    actions = ["revoke_devices", "purge_expired"]

    def revoke_devices(self, request, queryset):
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f"تم حذف {count} جهاز موثوق.", messages.WARNING)
    revoke_devices.short_description = "🗑️ حذف الأجهزة المحددة"

    def purge_expired(self, request, queryset):
        deleted, _ = TrustedDevice.objects.filter(expires_at__lte=timezone.now()).delete()
        self.message_user(request, f"تم حذف {deleted} جهاز منتهي.")
    purge_expired.short_description = "🧹 حذف الأجهزة المنتهية"