import json
import secrets
from datetime import date

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Profile(models.Model):
    GENDER_CHOICES = (
        ("male", "ذكر"),
        ("female", "أنثى"),
        ("other", "أخرى"),
        ("", "غير محدد"),
    )
    RELATIONSHIP_CHOICES = (
        ("single", "أعزب / عزباء"),
        ("engaged", "مخطوب / مخطوبة"),
        ("married", "متزوج / متزوجة"),
        ("divorced", "مطلق / مطلقة"),
        ("widowed", "أرمل / أرملة"),
        ("", "غير محدد"),
    )
    POSTS_PRIVACY = (
        ("public", "🌍 عامة — الجميع"),
        ("friends", "👥 الأصدقاء فقط"),
        ("private", "🔒 خاصة — أنا فقط"),
    )
    MESSAGES_PRIVACY = (
        ("everyone", "الجميع"),
        ("friends", "الأصدقاء فقط"),
        ("nobody", "لا أحد"),
    )
    FRIEND_REQ_PRIVACY = (
        ("everyone", "الجميع"),
        ("friends_of_friends", "أصدقاء الأصدقاء"),
        ("nobody", "لا أحد"),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile",
    )

    display_name = models.CharField(max_length=150, blank=True)
    bio = models.TextField(max_length=300, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    cover = models.ImageField(upload_to="covers/", blank=True, null=True)
    location = models.CharField(max_length=100, blank=True)
    hometown = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    phone = models.CharField(max_length=20, blank=True, unique=True, null=True)
    birthdate = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, default="")
    relationship_status = models.CharField(
        max_length=15, choices=RELATIONSHIP_CHOICES, blank=True, default="",
    )
    languages = models.CharField(max_length=200, blank=True)

    education = models.CharField(max_length=200, blank=True)
    job_title = models.CharField(max_length=100, blank=True)
    workplace = models.CharField(max_length=150, blank=True)
    interests = models.TextField(max_length=500, blank=True)

    following = models.ManyToManyField(
        "self", symmetrical=False, related_name="followers", blank=True,
    )

    is_verified = models.BooleanField(default=True)
    verification_token = models.CharField(max_length=64, blank=True, db_index=True)
    is_suspended = models.BooleanField(default=False)
    suspended_until = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.TextField(blank=True)
    warning_count = models.IntegerField(default=0)

    is_2fa_enabled = models.BooleanField(default=False)
    totp_secret = models.CharField(max_length=64, blank=True)
    backup_codes = models.TextField(blank=True)
    last_2fa_verified = models.DateTimeField(null=True, blank=True)

    posts_privacy = models.CharField(max_length=15, choices=POSTS_PRIVACY, default="public")
    messages_privacy = models.CharField(max_length=15, choices=MESSAGES_PRIVACY, default="everyone")
    friend_requests_privacy = models.CharField(max_length=20, choices=FRIEND_REQ_PRIVACY, default="everyone")
    show_email = models.BooleanField(default=False)
    show_phone = models.BooleanField(default=False)
    show_birthdate = models.BooleanField(default=True)
    show_relationship = models.BooleanField(default=True)
    allow_tagging = models.BooleanField(default=True)
    searchable = models.BooleanField(default=True)

    notify_messages = models.BooleanField(default=True)
    notify_followers = models.BooleanField(default=True)
    notify_likes = models.BooleanField(default=True)
    notify_comments = models.BooleanField(default=True)
    notify_group_posts = models.BooleanField(default=True)
    notify_page_posts = models.BooleanField(default=True)
    notify_friend_requests = models.BooleanField(default=True)
    email_notifications = models.BooleanField(default=False)

    theme_preference = models.CharField(
        max_length=10,
        choices=(("auto", "تلقائي"), ("light", "نهاري"), ("dark", "ليلي")),
        default="auto",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.username

    def name(self):
        return self.display_name.strip() or self.user.username

    def short_name(self):
        n = self.name()
        return n.split()[0] if n else ""

    def initials(self):
        parts = [p for p in self.name().split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][:1] + parts[1][:1]).upper()

    def is_currently_suspended(self):
        from django.utils import timezone
        if self.is_suspended:
            return True
        if self.suspended_until and self.suspended_until > timezone.now():
            return True
        return False

    def friends(self):
        from django.contrib.auth.models import User
        sent = Friendship.objects.filter(
            from_user=self.user, status="accepted"
        ).values_list("to_user", flat=True)
        received = Friendship.objects.filter(
            to_user=self.user, status="accepted"
        ).values_list("from_user", flat=True)
        return User.objects.filter(id__in=list(sent) + list(received))

    def friends_count(self):
        return self.friends().count()

    def pending_requests_count(self):
        return Friendship.objects.filter(to_user=self.user, status="pending").count()

    def unread_messages_count(self):
        return Message.objects.filter(
            conversation__participants=self.user,
            is_read=False,
            is_deleted=False,
        ).exclude(sender=self.user).count()

    def interests_list(self):
        if not self.interests:
            return []
        return [i.strip() for i in self.interests.split(",") if i.strip()]

    def languages_list(self):
        if not self.languages:
            return []
        return [i.strip() for i in self.languages.split(",") if i.strip()]

    def age(self):
        if not self.birthdate:
            return None
        today = date.today()
        return today.year - self.birthdate.year - (
            (today.month, today.day) < (self.birthdate.month, self.birthdate.day)
        )

    def birthdate_display(self):
        if not self.birthdate:
            return ""
        months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
                  "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
        return f"{self.birthdate.day} {months[self.birthdate.month - 1]} {self.birthdate.year}"

    def profile_completeness(self):
        fields = [
            self.display_name, self.bio, self.avatar, self.location,
            self.birthdate, self.education, self.job_title, self.interests,
            self.website, self.hometown, self.languages,
        ]
        filled = sum(1 for f in fields if f)
        return int((filled / len(fields)) * 100)

    def generate_totp_secret(self):
        import pyotp
        self.totp_secret = pyotp.random_base32()
        self.save(update_fields=["totp_secret"])
        return self.totp_secret

    def get_totp_uri(self):
        import pyotp
        if not self.totp_secret:
            return ""
        totp = pyotp.TOTP(self.totp_secret)
        return totp.provisioning_uri(
            name=self.user.email or self.user.username,
            issuer_name=getattr(settings, "TWO_FA_ISSUER", "WorldLink"),
        )

    def verify_totp(self, code):
        import pyotp
        if not self.totp_secret:
            return False
        totp = pyotp.TOTP(self.totp_secret)
        window = getattr(settings, "TWO_FA_VALID_WINDOW", 1)
        return totp.verify(code, valid_window=window)

    def generate_backup_codes(self, count=8):
        import hashlib
        codes = []
        hashed = []
        for _ in range(count):
            code = secrets.token_hex(4).upper()
            codes.append(code)
            hashed.append(hashlib.sha256(code.encode()).hexdigest())
        self.backup_codes = json.dumps(hashed)
        self.save(update_fields=["backup_codes"])
        return codes

    def verify_backup_code(self, code):
        import hashlib
        if not self.backup_codes:
            return False
        try:
            hashed_list = json.loads(self.backup_codes)
        except Exception:
            return False
        target = hashlib.sha256(code.strip().upper().encode()).hexdigest()
        if target in hashed_list:
            hashed_list.remove(target)
            self.backup_codes = json.dumps(hashed_list)
            self.save(update_fields=["backup_codes"])
            return True
        return False


class Post(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posts",
    )
    content = models.TextField(max_length=2000, blank=True)
    image = models.ImageField(upload_to="posts/covers/", blank=True, null=True)
    video = models.FileField(upload_to="posts/videos/", blank=True, null=True)
    repost_of = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="reposts",
    )
    is_quote = models.BooleanField(default=False)
    is_hidden_by_admin = models.BooleanField(default=False)
    hidden_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    likes = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="liked_posts", blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def total_likes(self):
        return self.likes.count()

    def total_comments(self):
        return self.comments.count()

    def total_reposts(self):
        return self.reposts.count()


class PostImage(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="posts/gallery/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comments",
    )
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies",
    )
    content = models.TextField(max_length=500)
    likes = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="liked_comments", blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def total_likes(self):
        return self.likes.count()

    def replies_count(self):
        return self.replies.count()

    def replies_chrono(self):
        return self.replies.order_by("created_at")


class Notification(models.Model):
    TYPES = (
        ("like", "إعجاب بمنشور"),
        ("comment", "تعليق"),
        ("follow", "متابعة"),
        ("repost", "إعادة نشر"),
        ("comment_like", "إعجاب بتعليق"),
        ("comment_reply", "رد على تعليق"),
        ("friend_request", "طلب صداقة"),
        ("friend_accept", "قبول صداقة"),
        ("warning", "إنذار إداري"),
        ("suspension", "تعليق حساب"),
        ("message", "رسالة خاصة"),
        ("group_join", "انضمام لمجموعة"),
        ("group_post", "منشور في مجموعة"),
        ("page_follow", "متابعة صفحة"),
        ("page_post", "منشور في صفحة"),
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_notifications",
    )
    notification_type = models.CharField(max_length=20, choices=TYPES)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True)
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, null=True, blank=True)
    message = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Friendship(models.Model):
    STATUS = (
        ("pending", "قيد الانتظار"),
        ("accepted", "مقبول"),
        ("declined", "مرفوض"),
    )
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="friend_requests_sent",
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="friend_requests_received",
    )
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("from_user", "to_user")
        ordering = ["-created_at"]


class UserRelation(models.Model):
    TYPES = (("mute", "كتم"), ("block", "حظر"))
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="relations_from",
    )
    target = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="relations_to",
    )
    relation_type = models.CharField(max_length=10, choices=TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "target", "relation_type")
        ordering = ["-created_at"]


class LoginAttempt(models.Model):
    username = models.CharField(max_length=150, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    success = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Bookmark(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookmarks",
    )
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="bookmarks")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "post")
        ordering = ["-created_at"]


class HiddenPost(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hidden_posts",
    )
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="hidden_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "post")


class Report(models.Model):
    REASONS = (
        ("spam", "محتوى مزعج / سبام"),
        ("harassment", "تحرش أو إساءة"),
        ("hate", "خطاب كراهية"),
        ("violence", "عنف"),
        ("misinformation", "معلومات مضللة"),
        ("other", "سبب آخر"),
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports_made",
    )
    post = models.ForeignKey(
        Post, on_delete=models.CASCADE, null=True, blank=True, related_name="reports",
    )
    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        null=True, blank=True, related_name="reports_received",
    )
    message = models.ForeignKey(
        "Message", on_delete=models.SET_NULL, null=True, blank=True, related_name="reports",
    )
    reason = models.CharField(max_length=20, choices=REASONS)
    details = models.TextField(blank=True, max_length=500)
    is_reviewed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Conversation(models.Model):
    MODES = (("normal", "عادية"), ("secret", "سرية 🔒"))
    DISAPPEAR_OPTIONS = (
        (0, "بدون اختفاء"),
        (300, "5 دقائق"),
        (3600, "ساعة"),
        (86400, "يوم"),
        (604800, "أسبوع"),
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="conversations",
    )
    mode = models.CharField(max_length=10, choices=MODES, default="normal")
    disappear_after = models.IntegerField(default=0, choices=DISAPPEAR_OPTIONS)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def last_message(self):
        return self.messages.filter(is_deleted=False).order_by("-created_at").first()

    def other_participant(self, user):
        return self.participants.exclude(id=user.id).first()

    def unread_count_for(self, user):
        return self.messages.filter(
            is_read=False, is_deleted=False,
        ).exclude(sender=user).count()

    def is_secret(self):
        return self.mode == "secret"


class Message(models.Model):
    TYPES = (
        ("text", "نص"),
        ("image", "صورة"),
        ("video", "فيديو"),
        ("audio", "صوت"),
        ("voice", "تسجيل صوتي"),
        ("file", "ملف"),
    )
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages",
    )
    content = models.TextField(max_length=2000, blank=True)
    message_type = models.CharField(max_length=10, choices=TYPES, default="text")
    file = models.FileField(upload_to="chat/files/", blank=True, null=True)
    reply_to = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="replies",
    )
    is_read = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def is_media(self):
        return self.message_type in ("image", "video", "audio", "voice", "file")

    def file_name(self):
        if self.file:
            return self.file.name.split("/")[-1]
        return ""

    def was_edited(self):
        return self.edited_at is not None


class Group(models.Model):
    PRIVACY = (("public", "عامة"), ("private", "خاصة"))
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(max_length=500, blank=True)
    avatar = models.ImageField(upload_to="groups/avatars/", blank=True, null=True)
    cover = models.ImageField(upload_to="groups/covers/", blank=True, null=True)
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_groups",
    )
    privacy = models.CharField(max_length=10, choices=PRIVACY, default="public")
    is_hidden_by_admin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name, allow_unicode=True) or "group"
            slug = base
            i = 1
            while Group.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{i}"
                i += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def members_count(self):
        return self.members.count()

    def posts_count(self):
        return self.posts.count()

    def is_member(self, user):
        if not user.is_authenticated:
            return False
        return self.members.filter(user=user).exists()

    def is_admin(self, user):
        if not user.is_authenticated:
            return False
        return self.members.filter(user=user, role="admin").exists()


class GroupMember(models.Model):
    ROLES = (("admin", "مشرف"), ("moderator", "مراقب"), ("member", "عضو"))
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="group_memberships",
    )
    role = models.CharField(max_length=10, choices=ROLES, default="member")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("group", "user")
        ordering = ["joined_at"]


class GroupPost(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="posts")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="group_posts",
    )
    content = models.TextField(max_length=2000, blank=True)
    image = models.ImageField(upload_to="groups/posts/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    likes = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="liked_group_posts", blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def total_likes(self):
        return self.likes.count()


class Page(models.Model):
    CATEGORIES = (
        ("business", "أعمال"),
        ("brand", "علامة تجارية"),
        ("community", "مجتمع"),
        ("public_figure", "شخصية عامة"),
        ("education", "تعليم"),
        ("tech", "تقنية"),
        ("other", "أخرى"),
    )
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    category = models.CharField(max_length=20, choices=CATEGORIES, default="other")
    description = models.TextField(max_length=500, blank=True)
    avatar = models.ImageField(upload_to="pages/avatars/", blank=True, null=True)
    cover = models.ImageField(upload_to="pages/covers/", blank=True, null=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_pages",
    )
    website = models.URLField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.CharField(max_length=200, blank=True)
    is_hidden_by_admin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name, allow_unicode=True) or "page"
            slug = base
            i = 1
            while Page.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{i}"
                i += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def followers_count(self):
        return self.followers.count()

    def posts_count(self):
        return self.posts.count()

    def is_followed_by(self, user):
        if not user.is_authenticated:
            return False
        return self.followers.filter(user=user).exists()

    def is_owner(self, user):
        return user.is_authenticated and self.owner == user


class PageFollower(models.Model):
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="followers")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="page_follows",
    )
    followed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("page", "user")
        ordering = ["-followed_at"]


class PagePost(models.Model):
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="posts")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="page_posts",
    )
    content = models.TextField(max_length=2000, blank=True)
    image = models.ImageField(upload_to="pages/posts/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    likes = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="liked_page_posts", blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def total_likes(self):
        return self.likes.count()


# ==================== سجل الأدمن ====================
class AdminLog(models.Model):
    ACTIONS = (
        ("login_success", "دخول ناجح"),
        ("login_fail", "محاولة دخول فاشلة"),
        ("logout", "خروج"),
        ("access_denied", "رفض وصول"),
        ("create", "إنشاء"),
        ("update", "تعديل"),
        ("delete", "حذف"),
        ("action", "إجراء جماعي"),
        ("other", "أخرى"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="admin_logs",
    )
    username_tried = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=20, choices=ACTIONS)
    target_model = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=50, blank=True)
    details = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    path = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "سجل إداري"
        verbose_name_plural = "السجل الإداري"


# ==================== الجلسات النشطة ====================
class UserSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="active_sessions",
    )
    session_key = models.CharField(max_length=64, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    device_type = models.CharField(max_length=20, blank=True)
    browser = models.CharField(max_length=50, blank=True)
    os = models.CharField(max_length=50, blank=True)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    is_current = models.BooleanField(default=False)
    last_activity = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-last_activity"]
        verbose_name = "جلسة مستخدم"
        verbose_name_plural = "الجلسات النشطة"

    def __str__(self):
        return f"{self.user.username} — {self.ip_address}"


# ==================== كشف الحسابات المزيفة ====================
class SuspiciousAccount(models.Model):
    LEVELS = (
        ("low", "منخفض"),
        ("medium", "متوسط"),
        ("high", "مرتفع"),
        ("critical", "حرج"),
    )
    STATUS = (
        ("pending", "بانتظار المراجعة"),
        ("cleared", "تم التأكد"),
        ("blocked", "محظور"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="suspicion_flags",
    )
    level = models.CharField(max_length=10, choices=LEVELS, default="low")
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    reason = models.TextField()
    signals = models.TextField(blank=True, help_text="JSON list of detected signals")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="reviewed_flags",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "حساب مشبوه"
        verbose_name_plural = "الحسابات المشبوهة"

    def __str__(self):
        return f"[{self.get_level_display()}] {self.user.username}"


# ==================== الأجهزة الموثوقة ====================
class TrustedDevice(models.Model):
    """
    جهاز تحقق عبره المستخدم بـ 2FA مؤخرًا.
    يمكنه تخطي 2FA لمدة 30 يومًا.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="trusted_devices",
    )
    token_hash = models.CharField(max_length=128, db_index=True)
    device_name = models.CharField(max_length=200, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    expires_at = models.DateTimeField(db_index=True)
    last_used_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-last_used_at"]
        verbose_name = "جهاز موثوق"
        verbose_name_plural = "الأجهزة الموثوقة"

    def __str__(self):
        return f"{self.user.username} — {self.device_name or 'جهاز'}"

    def is_expired(self):
        from django.utils import timezone
        return self.expires_at <= timezone.now()