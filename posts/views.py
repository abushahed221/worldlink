import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .crypto import decrypt_text
from .forms import (
    SignupForm, PostForm, CommentForm, ReportForm, QuoteForm,
    EmailOrPhoneLoginForm, ReportMessageForm, GroupForm, GroupPostForm,
    PageForm, PagePostForm, TwoFAVerifyForm, TwoFAEnableForm,
    ProfileBasicForm, ProfilePersonalForm, ProfileWorkForm, ProfileInterestsForm,
    PrivacySettingsForm, NotificationSettingsForm, AppearanceForm,
    AccountForm, DeleteAccountForm, ChangePasswordForm,
)
from .models import (
    Post, PostImage, Comment, Profile, Notification, Friendship, UserRelation,
    LoginAttempt, Bookmark, HiddenPost, Report, Conversation, Message,
    Group, GroupMember, GroupPost, Page, PageFollower, PagePost,
    TrustedDevice,
)
from .security_utils import looks_like_bot


def _blocked_or_muted_ids(user):
    return list(
        UserRelation.objects.filter(user=user).values_list("target_id", flat=True)
    )


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def _can_view_posts(viewer, owner):
    if viewer == owner:
        return True
    try:
        privacy = owner.profile.posts_privacy
    except Exception:
        return True
    if privacy == "public":
        return True
    if privacy == "private":
        return False
    if privacy == "friends":
        if not viewer.is_authenticated:
            return False
        return Friendship.objects.filter(
            Q(from_user=viewer, to_user=owner, status="accepted") |
            Q(from_user=owner, to_user=viewer, status="accepted")
        ).exists()
    return True


# ==================== تسجيل الدخول ====================
class SecureLoginView(LoginView):
    template_name = "posts/login.html"
    authentication_form = EmailOrPhoneLoginForm
    MAX_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15

    def get_client_ip(self):
        return _client_ip(self.request)

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST":
            identifier = request.POST.get("username", "").strip()
            ip = self.get_client_ip()
            since = timezone.now() - timedelta(minutes=self.LOCKOUT_MINUTES)
            fails = LoginAttempt.objects.filter(
                username=identifier, ip_address=ip,
                success=False, created_at__gte=since,
            ).count()
            if fails >= self.MAX_ATTEMPTS:
                messages.error(request, f"حظر مؤقت. حاول بعد {self.LOCKOUT_MINUTES} دقيقة.")
                return redirect("login")
        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        identifier = form.cleaned_data.get("username", "") or self.request.POST.get("username", "")
        LoginAttempt.objects.create(
            username=identifier, ip_address=self.get_client_ip(), success=False,
        )
        messages.error(self.request, "بيانات الدخول غير صحيحة.")
        return super().form_invalid(form)

    def form_valid(self, form):
        user = form.get_user()
        if not user.profile.is_verified:
            messages.error(self.request, "يجب تفعيل بريدك أولا.")
            return redirect("login")
        if user.profile.is_currently_suspended():
            reason = user.profile.suspension_reason or "لم يذكر سبب."
            messages.error(self.request, f"حسابك معلق. السبب: {reason}")
            return redirect("login")
        if user.profile.is_2fa_enabled:
            from .utils_2fa import is_device_trusted
            if is_device_trusted(self.request, user):
                LoginAttempt.objects.create(
                    username=form.cleaned_data.get("username", ""),
                    ip_address=self.get_client_ip(), success=True,
                )
                messages.success(self.request, "تم تسجيل الدخول (جهاز موثوق).")
                return super().form_valid(form)

            self.request.session["2fa_user_id"] = user.id
            self.request.session["2fa_next"] = self.get_success_url()
            LoginAttempt.objects.create(
                username=form.cleaned_data.get("username", ""),
                ip_address=self.get_client_ip(), success=False,
            )
            return redirect("twofa_verify")
        LoginAttempt.objects.create(
            username=form.cleaned_data.get("username", ""),
            ip_address=self.get_client_ip(), success=True,
        )
        messages.success(self.request, "تم تسجيل الدخول.")
        return super().form_valid(form)


# ==================== 2FA ====================
def twofa_verify(request):
    user_id = request.session.get("2fa_user_id")
    if not user_id:
        return redirect("login")
    user = User.objects.filter(id=user_id).first()
    if not user or not user.profile.is_2fa_enabled:
        request.session.pop("2fa_user_id", None)
        return redirect("login")

    if request.method == "POST":
        form = TwoFAVerifyForm(request.POST)
        remember = request.POST.get("remember_device") == "1"
        if form.is_valid():
            code = form.cleaned_data["code"].strip()
            if user.profile.verify_totp(code):
                return _complete_2fa_login(request, user, remember=remember)
            if user.profile.verify_backup_code(code):
                messages.info(request, "تم استخدام كود احتياطي.")
                return _complete_2fa_login(request, user, remember=remember)
            messages.error(request, "الرمز غير صحيح.")
    else:
        form = TwoFAVerifyForm()
    return render(request, "posts/login_2fa.html", {"form": form})


def _complete_2fa_login(request, user, remember=False):
    from .utils_2fa import create_trusted_device, set_trusted_cookie

    user.profile.last_2fa_verified = timezone.now()
    user.profile.save(update_fields=["last_2fa_verified"])
    next_url = request.session.pop("2fa_next", None) or settings.LOGIN_REDIRECT_URL
    request.session.pop("2fa_user_id", None)
    login(request, user, backend="posts.backends.EmailOrPhoneBackend")
    LoginAttempt.objects.create(
        username=user.username, ip_address=_client_ip(request), success=True,
    )

    response = redirect(next_url)
    if remember:
        device, raw_token = create_trusted_device(user, request)
        set_trusted_cookie(response, user.id, raw_token)
        messages.success(request, "تم تسجيل الدخول. تم تذكر هذا الجهاز لمدة 30 يومًا.")
    else:
        messages.success(request, "تم تسجيل الدخول.")
    return response


@login_required
def twofa_setup(request):
    profile = request.user.profile
    if profile.is_2fa_enabled:
        messages.info(request, "2FA مفعّل بالفعل.")
        return redirect("security_settings")
    if not profile.totp_secret:
        profile.generate_totp_secret()
    uri = profile.get_totp_uri()
    qr_data_url = ""
    try:
        import qrcode
        from io import BytesIO
        import base64
        img = qrcode.make(uri)
        buf = BytesIO()
        img.save(buf, format="PNG")
        qr_data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        pass
    return render(request, "posts/setup_2fa.html", {
        "qr_data_url": qr_data_url,
        "secret": profile.totp_secret,
        "form": TwoFAEnableForm(),
    })


@login_required
def twofa_enable(request):
    profile = request.user.profile
    if request.method != "POST":
        return redirect("twofa_setup")
    form = TwoFAEnableForm(request.POST)
    if not form.is_valid():
        messages.error(request, "أدخل رمزًا صحيحًا (6 أرقام).")
        return redirect("twofa_setup")
    code = form.cleaned_data["code"].strip()
    if not profile.verify_totp(code):
        messages.error(request, "الرمز غير صحيح.")
        return redirect("twofa_setup")
    profile.is_2fa_enabled = True
    profile.last_2fa_verified = timezone.now()
    codes = profile.generate_backup_codes(count=8)
    profile.save()
    messages.success(request, "تم تفعيل 2FA!")
    return render(request, "posts/setup_2fa_success.html", {"codes": codes})


@login_required
@require_POST
def twofa_disable(request):
    profile = request.user.profile
    password = request.POST.get("password", "")
    if not request.user.check_password(password):
        messages.error(request, "كلمة المرور غير صحيحة.")
        return redirect("security_settings")
    profile.is_2fa_enabled = False
    profile.totp_secret = ""
    profile.backup_codes = ""
    profile.save(update_fields=["is_2fa_enabled", "totp_secret", "backup_codes"])
    TrustedDevice.objects.filter(user=request.user).delete()
    messages.success(request, "تم تعطيل 2FA وحذف كل الأجهزة الموثوقة.")
    return redirect("security_settings")


@login_required
@require_POST
def twofa_regenerate_backup(request):
    profile = request.user.profile
    password = request.POST.get("password", "")
    if not request.user.check_password(password):
        messages.error(request, "كلمة المرور غير صحيحة.")
        return redirect("security_settings")
    codes = profile.generate_backup_codes(count=8)
    messages.success(request, "تم توليد أكواد جديدة.")
    return render(request, "posts/setup_2fa_success.html", {"codes": codes})


@login_required
def security_settings(request):
    profile = request.user.profile
    recent_logins = LoginAttempt.objects.filter(
        username__iexact=request.user.username
    ).order_by("-created_at")[:15]
    trusted_count = TrustedDevice.objects.filter(
        user=request.user, expires_at__gt=timezone.now(),
    ).count()
    return render(request, "posts/security_settings.html", {
        "profile": profile,
        "recent_logins": recent_logins,
        "trusted_count": trusted_count,
    })


# ==================== الأجهزة الموثوقة ====================
@login_required
def trusted_devices_list(request):
    from .utils_2fa import get_trusted_cookie_payload, _hash_token

    devices_qs = TrustedDevice.objects.filter(
        user=request.user,
        expires_at__gt=timezone.now(),
    ).order_by("-last_used_at")

    current_hash = None
    payload = get_trusted_cookie_payload(request)
    if payload and payload.get("uid") == request.user.id:
        token = payload.get("token")
        if token:
            current_hash = _hash_token(token)

    devices_data = []
    for d in devices_qs:
        devices_data.append({
            "obj": d,
            "is_current": bool(current_hash and d.token_hash == current_hash),
        })

    return render(request, "posts/trusted_devices.html", {
        "devices": devices_data,
    })


@login_required
@require_POST
def trusted_device_remove(request, pk):
    from .utils_2fa import (
        get_trusted_cookie_payload, _hash_token, clear_trusted_cookie,
    )

    device = TrustedDevice.objects.filter(pk=pk, user=request.user).first()
    if not device:
        messages.error(request, "الجهاز غير موجود.")
        return redirect("trusted_devices")

    is_current = False
    payload = get_trusted_cookie_payload(request)
    if payload and payload.get("uid") == request.user.id:
        token = payload.get("token")
        if token and _hash_token(token) == device.token_hash:
            is_current = True

    device.delete()
    messages.success(request, "تم حذف الجهاز.")

    response = redirect("trusted_devices")
    if is_current:
        clear_trusted_cookie(response)
        messages.info(request, "لأنك حذفت الجهاز الحالي، سيُطلب منك 2FA في المرة القادمة.")
    return response


@login_required
@require_POST
def trusted_devices_remove_all(request):
    from .utils_2fa import clear_trusted_cookie

    count = TrustedDevice.objects.filter(user=request.user).count()
    TrustedDevice.objects.filter(user=request.user).delete()
    messages.success(request, f"تم حذف {count} جهاز موثوق.")
    response = redirect("trusted_devices")
    clear_trusted_cookie(response)
    return response


# ==================== التحقق من البريد ====================
def _send_verification_email(request, user, token):
    verify_url = request.build_absolute_uri(reverse("verify_email", args=[token]))
    subject = "تفعيل حسابك في WorldLink"
    message = f"مرحبا {user.username},\n\nلتفعيل حسابك افتح:\n{verify_url}\n\n- WorldLink"
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)


def signup(request):
    if request.method == "POST":
        if looks_like_bot(request):
            messages.error(request, "تم رفض الطلب.")
            return redirect("signup")
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data["email"].lower()
            user.save()
            profile = user.profile
            profile.is_verified = True
            phone = form.cleaned_data.get("phone")
            if phone:
                profile.phone = phone
            profile.save()
            login(request, user, backend="posts.backends.EmailOrPhoneBackend")
            messages.success(request, f"مرحبًا بك {user.username}!")
            return redirect("home")
    else:
        form = SignupForm()
    return render(request, "posts/signup.html", {"form": form})

def verify_email_sent(request):
    return render(request, "posts/verify_email_sent.html")


def verify_email(request, token):
    profile = Profile.objects.filter(verification_token=token).first()
    if not profile:
        return render(request, "posts/verify_email_invalid.html", status=400)
    profile.is_verified = True
    profile.verification_token = ""
    profile.save()
    messages.success(request, "تم تفعيل بريدك!")
    return redirect("login")


# ==================== الرئيسية ====================
def home(request):
    hidden_ids = []
    blocked_ids = []
    if request.user.is_authenticated:
        hidden_ids = HiddenPost.objects.filter(user=request.user).values_list("post_id", flat=True)
        blocked_ids = _blocked_or_muted_ids(request.user)
        following_users = request.user.profile.following.values_list("user", flat=True)
        posts = Post.objects.filter(
            Q(author__in=following_users) | Q(author=request.user)
        ).exclude(author_id__in=blocked_ids).exclude(
            is_hidden_by_admin=True
        ).select_related("author", "repost_of__author").prefetch_related(
            "images"
        ).exclude(id__in=hidden_ids).distinct()
        if not posts.exists():
            posts = Post.objects.select_related("author", "repost_of__author").prefetch_related(
                "images"
            ).exclude(author_id__in=blocked_ids).exclude(is_hidden_by_admin=True).exclude(id__in=hidden_ids).all()
    else:
        posts = Post.objects.select_related("author", "repost_of__author").prefetch_related(
            "images"
        ).exclude(is_hidden_by_admin=True).all()
    return render(request, "posts/home.html", {"posts": posts[:50]})


def explore(request):
    posts = Post.objects.select_related("author", "repost_of__author").prefetch_related(
        "images"
    ).exclude(is_hidden_by_admin=True).all()[:100]
    return render(request, "posts/explore.html", {"posts": posts})


# ==================== المنشورات ====================
@login_required
def create_post(request):
    if request.method == "POST":
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            images = request.FILES.getlist("images")
            for img in images[:10]:
                PostImage.objects.create(post=post, image=img)
            messages.success(request, "تم نشر المنشور.")
            return redirect("home")
    else:
        form = PostForm()
    return render(request, "posts/create_post.html", {"form": form})


def post_detail(request, pk):
    post = get_object_or_404(
        Post.objects.select_related("author", "repost_of__author").prefetch_related("images"),
        pk=pk,
    )
    if not _can_view_posts(request.user, post.author) and post.author != request.user:
        messages.error(request, "لا يمكنك رؤية هذا المنشور — خصوصية الناشر.")
        return redirect("home")

    sort = request.GET.get("sort", "new")
    comments_qs = post.comments.filter(parent=None).select_related("author")
    if sort == "old":
        comments_qs = comments_qs.order_by("created_at")
    elif sort == "liked":
        comments_qs = comments_qs.annotate(
            num_likes=Count("likes", distinct=True)
        ).order_by("-num_likes", "-created_at")
    else:
        comments_qs = comments_qs.order_by("-created_at")
    top_comments = comments_qs.prefetch_related(
        "likes", "replies__author", "replies__likes"
    )
    form = CommentForm()
    is_bookmarked = False
    if request.user.is_authenticated:
        is_bookmarked = Bookmark.objects.filter(user=request.user, post=post).exists()

    if request.method == "POST" and request.user.is_authenticated:
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.post = post
            comment.author = request.user
            parent_id = request.POST.get("parent_id")
            if parent_id:
                parent = get_object_or_404(Comment, pk=parent_id)
                comment.parent = parent
                if parent.author != request.user:
                    Notification.objects.create(
                        recipient=parent.author, sender=request.user,
                        notification_type="comment_reply", post=post, comment=comment,
                    )
            elif post.author != request.user:
                Notification.objects.create(
                    recipient=post.author, sender=request.user,
                    notification_type="comment", post=post,
                )
            comment.save()
            url = reverse("post_detail", args=[post.pk]) + f"#comment-{comment.pk}"
            return redirect(url)

    return render(request, "posts/post_detail.html", {
        "post": post, "top_comments": top_comments, "form": form,
        "is_bookmarked": is_bookmarked, "sort": sort,
    })


@login_required
def edit_post(request, pk):
    post = get_object_or_404(Post, pk=pk, author=request.user)
    if request.method == "POST":
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            form.save()
            images = request.FILES.getlist("images")
            for img in images[:10]:
                PostImage.objects.create(post=post, image=img)
            messages.success(request, "تم التحديث.")
            url = reverse("post_detail", args=[post.pk]) + "#post-top"
            return redirect(url)
    else:
        form = PostForm(instance=post)
    return render(request, "posts/edit_post.html", {"form": form, "post": post})


@login_required
def delete_post_image(request, pk):
    img = get_object_or_404(PostImage, pk=pk, post__author=request.user)
    post_pk = img.post.pk
    img.delete()
    messages.success(request, "تم حذف الصورة.")
    return redirect("edit_post", pk=post_pk)


@login_required
def delete_post(request, pk):
    post = get_object_or_404(Post, pk=pk, author=request.user)
    if request.method == "POST":
        post.delete()
        messages.success(request, "تم الحذف.")
        return redirect("home")
    return render(request, "posts/delete_post.html", {"post": post})


@login_required
def quote_post(request, pk):
    original = get_object_or_404(Post, pk=pk)
    target = original.repost_of if original.repost_of else original
    if request.method == "POST":
        form = QuoteForm(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.repost_of = target
            post.is_quote = True
            post.save()
            if target.author != request.user:
                Notification.objects.create(
                    recipient=target.author, sender=request.user,
                    notification_type="repost", post=target,
                )
            messages.success(request, "تم اقتباس المنشور.")
            return redirect("home")
    else:
        form = QuoteForm()
    return render(request, "posts/quote_post.html", {"form": form, "original": target})


# ==================== التفاعل ====================
@login_required
def toggle_like(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if request.user in post.likes.all():
        post.likes.remove(request.user)
    else:
        post.likes.add(request.user)
        if post.author != request.user:
            Notification.objects.create(
                recipient=post.author, sender=request.user,
                notification_type="like", post=post,
            )
    return redirect(request.META.get("HTTP_REFERER", "home"))


@login_required
def repost(request, pk):
    original = get_object_or_404(Post, pk=pk)
    target = original.repost_of if original.repost_of else original
    existing = Post.objects.filter(author=request.user, repost_of=target, is_quote=False).first()
    if existing:
        existing.delete()
        messages.info(request, "تم إلغاء إعادة النشر.")
    else:
        Post.objects.create(author=request.user, repost_of=target, content="", is_quote=False)
        if target.author != request.user:
            Notification.objects.create(
                recipient=target.author, sender=request.user,
                notification_type="repost", post=target,
            )
        messages.success(request, "تمت إعادة النشر.")
    return redirect(request.META.get("HTTP_REFERER", "home"))


@login_required
def toggle_bookmark(request, pk):
    post = get_object_or_404(Post, pk=pk)
    bm = Bookmark.objects.filter(user=request.user, post=post).first()
    if bm:
        bm.delete()
        messages.info(request, "تم إزالة الحفظ.")
    else:
        Bookmark.objects.create(user=request.user, post=post)
        messages.success(request, "تم الحفظ.")
    return redirect(request.META.get("HTTP_REFERER", "home"))


@login_required
def bookmarks_list(request):
    bookmarks = request.user.bookmarks.select_related(
        "post__author", "post__repost_of__author"
    ).prefetch_related("post__images").all()
    posts = [bm.post for bm in bookmarks]
    return render(request, "posts/bookmarks.html", {"posts": posts})


@login_required
def hide_post(request, pk):
    post = get_object_or_404(Post, pk=pk)
    HiddenPost.objects.get_or_create(user=request.user, post=post)
    messages.info(request, "تم إخفاء المنشور.")
    referer = request.META.get("HTTP_REFERER") or reverse("home")
    sep = "&" if "?" in referer else "?"
    return redirect(f"{referer}{sep}just_hidden={post.pk}")


@login_required
def unhide_post(request, pk):
    post = get_object_or_404(Post, pk=pk)
    HiddenPost.objects.filter(user=request.user, post=post).delete()
    messages.success(request, "تم استرجاع المنشور.")
    return redirect(request.META.get("HTTP_REFERER", "home"))


@login_required
def hide_all_from_user(request, username):
    target = get_object_or_404(User, username=username)
    for p in Post.objects.filter(author=target):
        HiddenPost.objects.get_or_create(user=request.user, post=p)
    messages.info(request, f"تم إخفاء كل منشورات {target.username}.")
    return redirect("home")


@login_required
def mute_user(request, username):
    target = get_object_or_404(User, username=username)
    if target == request.user:
        return redirect("profile", username=username)
    UserRelation.objects.get_or_create(user=request.user, target=target, relation_type="mute")
    messages.info(request, f"تم كتم {target.username}.")
    return redirect(request.META.get("HTTP_REFERER", "home"))


@login_required
def unmute_user(request, username):
    target = get_object_or_404(User, username=username)
    UserRelation.objects.filter(user=request.user, target=target, relation_type="mute").delete()
    messages.info(request, f"تم إلغاء كتم {target.username}.")
    return redirect(request.META.get("HTTP_REFERER", "home"))


@login_required
def block_user(request, username):
    target = get_object_or_404(User, username=username)
    if target == request.user:
        return redirect("profile", username=username)
    UserRelation.objects.get_or_create(user=request.user, target=target, relation_type="block")
    Friendship.objects.filter(
        Q(from_user=request.user, to_user=target) | Q(from_user=target, to_user=request.user)
    ).delete()
    request.user.profile.following.remove(target.profile)
    messages.info(request, f"تم حظر {target.username}.")
    return redirect("home")


@login_required
def unblock_user(request, username):
    target = get_object_or_404(User, username=username)
    UserRelation.objects.filter(user=request.user, target=target, relation_type="block").delete()
    messages.success(request, f"تم إلغاء حظر {target.username}.")
    return redirect("profile", username=username)


# ==================== التعليقات ====================
@login_required
def comment_like(request, pk):
    comment = get_object_or_404(Comment, pk=pk)
    if request.user in comment.likes.all():
        comment.likes.remove(request.user)
    else:
        comment.likes.add(request.user)
        if comment.author != request.user:
            Notification.objects.create(
                recipient=comment.author, sender=request.user,
                notification_type="comment_like",
                post=comment.post, comment=comment,
            )
    url = reverse("post_detail", args=[comment.post.pk]) + f"#comment-{comment.pk}"
    return redirect(url)


@login_required
def comment_edit(request, pk):
    comment = get_object_or_404(Comment, pk=pk, author=request.user)
    if request.method == "POST":
        form = CommentForm(request.POST, instance=comment)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث التعليق.")
            url = reverse("post_detail", args=[comment.post.pk]) + f"#comment-{comment.pk}"
            return redirect(url)
    else:
        form = CommentForm(instance=comment)
    return render(request, "posts/comment_edit.html", {"form": form, "comment": comment})


@login_required
def comment_delete(request, pk):
    comment = get_object_or_404(Comment, pk=pk, author=request.user)
    post_pk = comment.post.pk
    comment.delete()
    messages.success(request, "تم حذف التعليق.")
    return redirect("post_detail", pk=post_pk)


# ==================== الأصدقاء ====================
@login_required
def friends_list(request):
    friends = request.user.profile.friends()
    return render(request, "posts/friends.html", {"friends": friends})


@login_required
def friend_requests_list(request):
    requests = Friendship.objects.filter(
        to_user=request.user, status="pending"
    ).select_related("from_user")
    sent = Friendship.objects.filter(
        from_user=request.user, status="pending"
    ).select_related("to_user")
    return render(request, "posts/friend_requests.html", {
        "requests": requests, "sent": sent,
    })


@login_required
def send_friend_request(request, username):
    target = get_object_or_404(User, username=username)
    if target == request.user:
        return redirect("profile", username=username)

    tp = target.profile
    if tp.friend_requests_privacy == "nobody":
        messages.error(request, "هذا المستخدم لا يستقبل طلبات صداقة.")
        return redirect("profile", username=username)
    if tp.friend_requests_privacy == "friends_of_friends":
        my_friends = set(request.user.profile.friends().values_list("id", flat=True))
        their_friends = set(target.profile.friends().values_list("id", flat=True))
        if not (my_friends & their_friends):
            messages.error(request, "لا يمكن إرسال الطلب — ليس لديكم أصدقاء مشتركون.")
            return redirect("profile", username=username)

    existing = Friendship.objects.filter(
        Q(from_user=request.user, to_user=target) |
        Q(from_user=target, to_user=request.user)
    ).first()
    if existing:
        messages.info(request, "توجد علاقة مسبقة أو طلب معلق.")
    else:
        Friendship.objects.create(from_user=request.user, to_user=target)
        Notification.objects.create(
            recipient=target, sender=request.user,
            notification_type="friend_request",
        )
        messages.success(request, f"تم إرسال طلب صداقة إلى {target.username}.")
    return redirect("profile", username=username)


@login_required
def accept_friend_request(request, pk):
    friendship = get_object_or_404(Friendship, pk=pk, to_user=request.user, status="pending")
    friendship.status = "accepted"
    friendship.save()
    Notification.objects.create(
        recipient=friendship.from_user, sender=request.user,
        notification_type="friend_accept",
    )
    messages.success(request, f"تم قبول صداقة {friendship.from_user.username}.")
    return redirect("friend_requests")


@login_required
def decline_friend_request(request, pk):
    friendship = get_object_or_404(Friendship, pk=pk, to_user=request.user, status="pending")
    friendship.status = "declined"
    friendship.save()
    messages.info(request, "تم رفض الطلب.")
    return redirect("friend_requests")


@login_required
def remove_friend(request, username):
    target = get_object_or_404(User, username=username)
    Friendship.objects.filter(
        Q(from_user=request.user, to_user=target, status="accepted") |
        Q(from_user=target, to_user=request.user, status="accepted")
    ).delete()
    messages.info(request, "تمت إزالة الصداقة.")
    return redirect("profile", username=username)


# ==================== الإبلاغ ====================
@login_required
def report_post(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if request.method == "POST":
        form = ReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.reporter = request.user
            report.post = post
            report.reported_user = post.author
            report.save()
            messages.success(request, "تم استلام الإبلاغ.")
            return redirect("post_detail", pk=post.pk)
    else:
        form = ReportForm()
    return render(request, "posts/report_post.html", {"form": form, "post": post})


@login_required
def report_message(request, pk):
    msg = get_object_or_404(Message, pk=pk)
    if request.user not in msg.conversation.participants.all():
        return redirect("home")
    if request.method == "POST":
        form = ReportMessageForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.reporter = request.user
            report.reported_user = msg.sender
            report.message = msg
            report.save()
            messages.success(request, "تم استلام الإبلاغ.")
            return redirect("chat_room", pk=msg.conversation.pk)
    else:
        form = ReportMessageForm()
    return render(request, "posts/report_message.html", {"form": form, "msg": msg})


# ==================== الملف الشخصي ====================
def profile_view(request, username):
    user_obj = get_object_or_404(User, username=username)
    profile = user_obj.profile
    can_see = _can_view_posts(request.user, user_obj)
    if can_see:
        posts = user_obj.posts.select_related("author", "repost_of__author").prefetch_related(
            "images"
        ).exclude(is_hidden_by_admin=True).all()
    else:
        posts = []

    is_following = False
    is_friend = False
    friend_status = None
    is_muted = False
    is_blocked = False
    if request.user.is_authenticated and request.user != user_obj:
        is_following = request.user.profile.following.filter(user=user_obj).exists()
        fs = Friendship.objects.filter(
            Q(from_user=request.user, to_user=user_obj) |
            Q(from_user=user_obj, to_user=request.user)
        ).first()
        if fs:
            friend_status = fs.status
            if fs.status == "accepted":
                is_friend = True
        is_muted = UserRelation.objects.filter(
            user=request.user, target=user_obj, relation_type="mute"
        ).exists()
        is_blocked = UserRelation.objects.filter(
            user=request.user, target=user_obj, relation_type="block"
        ).exists()
    return render(request, "posts/profile.html", {
        "profile_user": user_obj, "profile": profile, "posts": posts,
        "is_following": is_following, "is_friend": is_friend,
        "friend_status": friend_status, "is_muted": is_muted, "is_blocked": is_blocked,
        "followers_count": profile.followers.count(),
        "following_count": profile.following.count(),
        "friends_count": profile.friends_count(),
        "can_see": can_see,
    })


@login_required
def toggle_follow(request, username):
    user_obj = get_object_or_404(User, username=username)
    if request.user == user_obj:
        return redirect("profile", username=username)
    my_profile = request.user.profile
    if my_profile.following.filter(user=user_obj).exists():
        my_profile.following.remove(user_obj.profile)
    else:
        my_profile.following.add(user_obj.profile)
        Notification.objects.create(
            recipient=user_obj, sender=request.user, notification_type="follow",
        )
    return redirect("profile", username=username)


@login_required
def edit_profile(request):
    return redirect("settings_profile")


# ==================== الإعدادات ====================
@login_required
def settings_index(request):
    profile = request.user.profile
    return render(request, "posts/settings/index.html", {"profile": profile})


@login_required
def settings_profile(request):
    profile = request.user.profile
    if request.method == "POST":
        form = ProfileBasicForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث المعلومات الأساسية.")
            return redirect("settings_profile")
    else:
        form = ProfileBasicForm(instance=profile)
    return render(request, "posts/settings/profile.html", {"form": form, "profile": profile})


@login_required
def settings_personal(request):
    profile = request.user.profile
    if request.method == "POST":
        form = ProfilePersonalForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث المعلومات الشخصية.")
            return redirect("settings_personal")
    else:
        form = ProfilePersonalForm(instance=profile)
    return render(request, "posts/settings/personal.html", {"form": form, "profile": profile})


@login_required
def settings_work(request):
    profile = request.user.profile
    if request.method == "POST":
        form = ProfileWorkForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث معلومات العمل.")
            return redirect("settings_work")
    else:
        form = ProfileWorkForm(instance=profile)
    return render(request, "posts/settings/work.html", {"form": form, "profile": profile})


@login_required
def settings_interests(request):
    profile = request.user.profile
    if request.method == "POST":
        form = ProfileInterestsForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث الاهتمامات.")
            return redirect("settings_interests")
    else:
        form = ProfileInterestsForm(instance=profile)
    return render(request, "posts/settings/interests.html", {"form": form, "profile": profile})


@login_required
def settings_privacy(request):
    profile = request.user.profile
    if request.method == "POST":
        form = PrivacySettingsForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث إعدادات الخصوصية.")
            return redirect("settings_privacy")
    else:
        form = PrivacySettingsForm(instance=profile)
    return render(request, "posts/settings/privacy.html", {"form": form, "profile": profile})


@login_required
def settings_notifications(request):
    profile = request.user.profile
    if request.method == "POST":
        form = NotificationSettingsForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث إعدادات الإشعارات.")
            return redirect("settings_notifications")
    else:
        form = NotificationSettingsForm(instance=profile)
    return render(request, "posts/settings/notifications.html", {"form": form, "profile": profile})


@login_required
def settings_appearance(request):
    profile = request.user.profile
    if request.method == "POST":
        form = AppearanceForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث المظهر.")
            return redirect("settings_appearance")
    else:
        form = AppearanceForm(instance=profile)
    return render(request, "posts/settings/appearance.html", {"form": form, "profile": profile})


@login_required
def settings_account(request):
    user = request.user
    account_form = AccountForm(instance=user, initial={"phone": user.profile.phone or ""})
    password_form = ChangePasswordForm(user=user)

    if request.method == "POST":
        if "save_account" in request.POST:
            account_form = AccountForm(request.POST, instance=user)
            if account_form.is_valid():
                account_form.save()
                messages.success(request, "تم تحديث بيانات الحساب.")
                return redirect("settings_account")
        elif "change_password" in request.POST:
            password_form = ChangePasswordForm(user=user, data=request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "تم تغيير كلمة المرور بنجاح.")
                return redirect("settings_account")

    return render(request, "posts/settings/account.html", {
        "account_form": account_form,
        "password_form": password_form,
    })


@login_required
def settings_delete_account(request):
    if request.method == "POST":
        form = DeleteAccountForm(request.POST)
        if form.is_valid():
            if not request.user.check_password(form.cleaned_data["password"]):
                messages.error(request, "كلمة المرور غير صحيحة.")
                return redirect("settings_delete_account")
            username = request.user.username
            request.user.delete()
            messages.success(request, f"تم حذف الحساب {username} نهائيًا.")
            return redirect("home")
    else:
        form = DeleteAccountForm()
    return render(request, "posts/settings/delete_account.html", {"form": form})


# ==================== المحادثات ====================
@login_required
def chat_list(request):
    conversations = request.user.conversations.prefetch_related(
        "participants", "messages"
    ).order_by("-updated_at")
    return render(request, "posts/chat_list.html", {"conversations": conversations})


@login_required
def start_chat(request, username):
    target = get_object_or_404(User, username=username)
    if target == request.user:
        messages.info(request, "لا يمكنك بدء محادثة مع نفسك.")
        return redirect("chat_list")

    tp = target.profile
    if tp.messages_privacy == "nobody":
        messages.error(request, "هذا المستخدم لا يستقبل رسائل.")
        return redirect("profile", username=username)
    if tp.messages_privacy == "friends":
        if not Friendship.objects.filter(
            Q(from_user=request.user, to_user=target, status="accepted") |
            Q(from_user=target, to_user=request.user, status="accepted")
        ).exists():
            messages.error(request, "يمكن للأصدقاء فقط مراسلة هذا المستخدم.")
            return redirect("profile", username=username)

    if UserRelation.objects.filter(
        Q(user=request.user, target=target, relation_type="block") |
        Q(user=target, target=request.user, relation_type="block")
    ).exists():
        messages.error(request, "لا يمكن بدء المحادثة بسبب وجود حظر.")
        return redirect("profile", username=username)

    conv = Conversation.objects.filter(participants=request.user).filter(
        participants=target
    ).first()
    if not conv:
        conv = Conversation.objects.create()
        conv.participants.add(request.user, target)
    return redirect("chat_room", pk=conv.pk)


@login_required
def chat_room(request, pk):
    conv = get_object_or_404(Conversation, pk=pk, participants=request.user)
    other = conv.other_participant(request.user)
    conv.messages.exclude(sender=request.user).update(is_read=True)

    raw_messages = conv.messages.select_related(
        "sender", "reply_to__sender"
    ).filter(is_deleted=False)
    messages_list = []
    for m in raw_messages:
        m.decrypted = decrypt_text(m.content)
        reply_decrypted = None
        if m.reply_to:
            reply_decrypted = decrypt_text(m.reply_to.content)
        messages_list.append({"obj": m, "text": m.decrypted, "reply_text": reply_decrypted})

    return render(request, "posts/chat_room.html", {
        "conversation": conv,
        "other": other,
        "messages_list": messages_list,
    })


@login_required
@require_POST
def set_conversation_mode(request, pk):
    conv = get_object_or_404(Conversation, pk=pk, participants=request.user)
    mode = request.POST.get("mode", "normal")
    if mode not in ("normal", "secret"):
        mode = "normal"
    conv.mode = mode
    conv.save(update_fields=["mode"])
    messages.success(request, "تم تحديث وضع المحادثة.")
    return redirect("chat_room", pk=conv.pk)


@login_required
@require_POST
def set_disappear(request, pk):
    conv = get_object_or_404(Conversation, pk=pk, participants=request.user)
    try:
        seconds = int(request.POST.get("seconds", 0))
    except ValueError:
        seconds = 0
    valid = [0, 300, 3600, 86400, 604800]
    if seconds not in valid:
        seconds = 0
    conv.disappear_after = seconds
    conv.save(update_fields=["disappear_after"])
    messages.success(request, "تم تحديث وقت الاختفاء.")
    return redirect("chat_room", pk=conv.pk)


@login_required
def delete_conversation(request, pk):
    conv = get_object_or_404(Conversation, pk=pk, participants=request.user)
    conv.messages.all().delete()
    conv.delete()
    messages.success(request, "تم حذف المحادثة.")
    return redirect("chat_list")


@login_required
@require_POST
def upload_chat_file(request, pk):
    conv = get_object_or_404(Conversation, pk=pk, participants=request.user)
    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"ok": False, "error": "لا يوجد ملف"}, status=400)
    if f.size > 25 * 1024 * 1024:
        return JsonResponse({"ok": False, "error": "الملف كبير (25MB كحد أقصى)"}, status=400)
    name = f.name.lower()
    ct = (f.content_type or "").lower()
    if name.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
        mtype = "image"
    elif name.endswith((".mp4", ".webm", ".mov", ".mkv")):
        mtype = "video"
    elif name.endswith((".mp3", ".wav", ".ogg", ".m4a")):
        mtype = "audio"
    elif "audio" in ct:
        mtype = "voice"
    else:
        mtype = "file"
    msg = Message.objects.create(
        conversation=conv, sender=request.user,
        message_type=mtype, file=f,
    )
    conv.updated_at = timezone.now()
    conv.save(update_fields=["updated_at"])
    return JsonResponse({
        "ok": True, "message_id": msg.id, "message_type": mtype,
        "file_url": msg.file.url, "file_name": msg.file_name(),
    })


# ==================== المجموعات ====================
def group_list(request):
    query = request.GET.get("q", "").strip()
    groups = Group.objects.exclude(is_hidden_by_admin=True).annotate(
        members_cnt=Count("members", distinct=True),
        posts_cnt=Count("posts", distinct=True),
    )
    if query:
        groups = groups.filter(Q(name__icontains=query) | Q(description__icontains=query))
    groups = groups.order_by("-members_cnt", "-created_at")[:60]
    return render(request, "posts/group_list.html", {"groups": groups, "query": query})


def group_detail(request, slug):
    group = get_object_or_404(Group, slug=slug)
    if group.is_hidden_by_admin:
        messages.error(request, "هذه المجموعة محجوبة.")
        return redirect("group_list")
    is_member = group.is_member(request.user)
    is_admin = group.is_admin(request.user)
    can_view_posts = (group.privacy == "public") or is_member
    if can_view_posts:
        posts = group.posts.select_related("author").all()[:50]
    else:
        posts = []
    form = GroupPostForm() if is_member else None
    if request.method == "POST" and is_member:
        form = GroupPostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.group = group
            post.author = request.user
            post.save()
            for m in group.members.exclude(user=request.user).select_related("user")[:500]:
                Notification.objects.create(
                    recipient=m.user, sender=request.user,
                    notification_type="group_post",
                    message=f"منشور جديد في {group.name}",
                )
            messages.success(request, "تم نشر المنشور.")
            return redirect("group_detail", slug=group.slug)
    return render(request, "posts/group_detail.html", {
        "group": group, "is_member": is_member, "is_admin": is_admin,
        "can_view_posts": can_view_posts, "posts": posts, "form": form,
    })


@login_required
def group_create(request):
    if request.method == "POST":
        form = GroupForm(request.POST, request.FILES)
        if form.is_valid():
            group = form.save(commit=False)
            group.creator = request.user
            group.save()
            GroupMember.objects.create(group=group, user=request.user, role="admin")
            messages.success(request, f"تم إنشاء مجموعة {group.name}.")
            return redirect("group_detail", slug=group.slug)
    else:
        form = GroupForm()
    return render(request, "posts/group_create.html", {"form": form})


@login_required
def group_join(request, slug):
    group = get_object_or_404(Group, slug=slug)
    if group.is_member(request.user):
        messages.info(request, "أنت عضو بالفعل.")
    else:
        GroupMember.objects.create(group=group, user=request.user, role="member")
        if group.creator != request.user:
            Notification.objects.create(
                recipient=group.creator, sender=request.user,
                notification_type="group_join",
                message=f"انضم إلى {group.name}",
            )
        messages.success(request, f"انضممت إلى {group.name}.")
    return redirect("group_detail", slug=slug)


@login_required
def group_leave(request, slug):
    group = get_object_or_404(Group, slug=slug)
    if group.creator == request.user:
        messages.error(request, "لا يمكنك مغادرة مجموعة أنت منشئها.")
        return redirect("group_detail", slug=slug)
    GroupMember.objects.filter(group=group, user=request.user).delete()
    messages.info(request, f"غادرت {group.name}.")
    return redirect("group_list")


@login_required
def group_members(request, slug):
    group = get_object_or_404(Group, slug=slug)
    if group.privacy == "private" and not group.is_member(request.user):
        messages.error(request, "هذه المجموعة خاصة.")
        return redirect("group_list")
    members = group.members.select_related("user", "user__profile").order_by("role", "joined_at")
    is_admin = group.is_admin(request.user)
    return render(request, "posts/group_members.html", {
        "group": group, "members": members, "is_admin": is_admin,
    })


@login_required
@require_POST
def group_remove_member(request, slug, username):
    group = get_object_or_404(Group, slug=slug)
    if not group.is_admin(request.user):
        messages.error(request, "غير مسموح.")
        return redirect("group_detail", slug=slug)
    target = get_object_or_404(User, username=username)
    if target == group.creator:
        messages.error(request, "لا يمكن إزالة المنشئ.")
        return redirect("group_members", slug=slug)
    GroupMember.objects.filter(group=group, user=target).delete()
    messages.success(request, f"تم إزالة {target.username}.")
    return redirect("group_members", slug=slug)


@login_required
def group_delete_post(request, slug, pk):
    group = get_object_or_404(Group, slug=slug)
    post = get_object_or_404(GroupPost, pk=pk, group=group)
    if post.author != request.user and not group.is_admin(request.user):
        messages.error(request, "غير مسموح.")
        return redirect("group_detail", slug=slug)
    post.delete()
    messages.success(request, "تم حذف المنشور.")
    return redirect("group_detail", slug=slug)


@login_required
def group_post_like(request, slug, pk):
    group = get_object_or_404(Group, slug=slug)
    post = get_object_or_404(GroupPost, pk=pk, group=group)
    if request.user in post.likes.all():
        post.likes.remove(request.user)
    else:
        post.likes.add(request.user)
    return redirect("group_detail", slug=slug)


# ==================== الصفحات ====================
def page_list(request):
    query = request.GET.get("q", "").strip()
    category = request.GET.get("cat", "").strip()
    pages = Page.objects.exclude(is_hidden_by_admin=True).annotate(
        followers_cnt=Count("followers", distinct=True),
    )
    if query:
        pages = pages.filter(Q(name__icontains=query) | Q(description__icontains=query))
    if category:
        pages = pages.filter(category=category)
    pages = pages.order_by("-followers_cnt", "-created_at")[:60]
    return render(request, "posts/page_list.html", {
        "pages": pages, "query": query, "category": category,
        "categories": Page.CATEGORIES,
    })


def page_detail(request, slug):
    page = get_object_or_404(Page, slug=slug)
    if page.is_hidden_by_admin:
        messages.error(request, "هذه الصفحة محجوبة.")
        return redirect("page_list")
    is_owner = page.is_owner(request.user)
    is_following = page.is_followed_by(request.user)
    posts = page.posts.select_related("author", "page").all()[:50]
    form = PagePostForm() if is_owner else None
    if request.method == "POST" and is_owner:
        form = PagePostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.page = page
            post.author = request.user
            post.save()
            for f in page.followers.exclude(user=request.user).select_related("user")[:500]:
                Notification.objects.create(
                    recipient=f.user, sender=request.user,
                    notification_type="page_post",
                    message=f"منشور جديد في {page.name}",
                )
            messages.success(request, "تم نشر المنشور.")
            return redirect("page_detail", slug=page.slug)
    return render(request, "posts/page_detail.html", {
        "page": page, "is_owner": is_owner,
        "is_following": is_following, "posts": posts, "form": form,
    })


@login_required
def page_create(request):
    if request.method == "POST":
        form = PageForm(request.POST, request.FILES)
        if form.is_valid():
            page = form.save(commit=False)
            page.owner = request.user
            page.save()
            messages.success(request, f"تم إنشاء صفحة {page.name}.")
            return redirect("page_detail", slug=page.slug)
    else:
        form = PageForm()
    return render(request, "posts/page_create.html", {"form": form})


@login_required
def page_edit(request, slug):
    page = get_object_or_404(Page, slug=slug)
    if not page.is_owner(request.user):
        messages.error(request, "غير مسموح.")
        return redirect("page_detail", slug=slug)
    if request.method == "POST":
        form = PageForm(request.POST, request.FILES, instance=page)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث الصفحة.")
            return redirect("page_detail", slug=page.slug)
    else:
        form = PageForm(instance=page)
    return render(request, "posts/page_create.html", {"form": form, "page": page})


@login_required
def page_follow(request, slug):
    page = get_object_or_404(Page, slug=slug)
    if page.is_followed_by(request.user):
        PageFollower.objects.filter(page=page, user=request.user).delete()
        messages.info(request, f"ألغيت متابعة {page.name}.")
    else:
        PageFollower.objects.create(page=page, user=request.user)
        if page.owner != request.user:
            Notification.objects.create(
                recipient=page.owner, sender=request.user,
                notification_type="page_follow",
                message=f"بدأ متابعة {page.name}",
            )
        messages.success(request, f"تابعت {page.name}.")
    return redirect("page_detail", slug=slug)


@login_required
def page_delete_post(request, slug, pk):
    page = get_object_or_404(Page, slug=slug)
    post = get_object_or_404(PagePost, pk=pk, page=page)
    if not page.is_owner(request.user):
        messages.error(request, "غير مسموح.")
        return redirect("page_detail", slug=slug)
    post.delete()
    messages.success(request, "تم حذف المنشور.")
    return redirect("page_detail", slug=slug)


@login_required
def page_post_like(request, slug, pk):
    page = get_object_or_404(Page, slug=slug)
    post = get_object_or_404(PagePost, pk=pk, page=page)
    if request.user in post.likes.all():
        post.likes.remove(request.user)
    else:
        post.likes.add(request.user)
    return redirect("page_detail", slug=slug)


# ==================== أخرى ====================
def offline(request):
    return render(request, "posts/offline.html")


def ratelimited_view(request, exception=None):
    return render(request, "posts/ratelimited.html", status=429)


def search(request):
    query = request.GET.get("q", "").strip()
    users = []
    posts = []
    groups = []
    pages = []
    if query:
        users = User.objects.filter(
            username__icontains=query, profile__searchable=True,
        )[:20]
        posts = Post.objects.filter(content__icontains=query).exclude(
            is_hidden_by_admin=True
        ).select_related("author")[:50]
        groups = Group.objects.filter(
            name__icontains=query, is_hidden_by_admin=False
        )[:20]
        pages = Page.objects.filter(
            name__icontains=query, is_hidden_by_admin=False
        )[:20]
    return render(request, "posts/search.html", {
        "query": query, "users": users, "posts": posts,
        "groups": groups, "pages": pages,
    })


@login_required
def notifications_list(request):
    notifs = request.user.notifications.select_related(
        "sender", "post", "comment"
    ).all()[:100]
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, "posts/notifications.html", {"notifications": notifs})


# ==================== تنزيل بياناتي (GDPR) ====================
@login_required
def data_export(request):
    from .gdpr_utils import build_user_data, to_json_bytes
    import json

    data = build_user_data(request.user)
    content = to_json_bytes(data)

    from django.http import HttpResponse
    response = HttpResponse(content, content_type="application/json; charset=utf-8")
    filename = f"worldlink_data_{request.user.username}_{timezone.now().strftime('%Y%m%d')}.json"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def data_export_preview(request):
    """معاينة حجم البيانات قبل التنزيل."""
    from .models import (
        Post, Comment, Conversation, Message, GroupPost, PagePost,
    )
    stats = {
        "posts": Post.objects.filter(author=request.user).count(),
        "comments": Comment.objects.filter(author=request.user).count(),
        "messages": Message.objects.filter(sender=request.user, is_deleted=False).count(),
        "group_posts": GroupPost.objects.filter(author=request.user).count(),
        "page_posts": PagePost.objects.filter(author=request.user).count(),
    }
    return render(request, "posts/data_export.html", {"stats": stats})
