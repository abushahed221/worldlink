from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

from .models import (
    Post, Comment, Profile, Report, Message,
    Group, GroupPost, Page, PagePost,
)
from .security_utils import is_disposable_email, is_suspicious_username


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True, label=_("البريد الإلكتروني"))
    phone = forms.CharField(
        required=False, max_length=20, label=_("رقم الهاتف (اختياري)"),
        widget=forms.TextInput(attrs={"placeholder": "+967xxxxxxxxx"}),
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(_("اسم المستخدم محجوز."))
        if is_suspicious_username(username):
            raise forms.ValidationError(_("هذا الاسم غير صالح. اختر اسمًا آخر."))
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("هذا البريد مسجّل مسبقًا."))
        if is_disposable_email(email):
            raise forms.ValidationError(_("لا نسمح بالبريد المؤقت. استخدم بريدًا حقيقيًا."))
        return email

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if phone and Profile.objects.filter(phone=phone).exists():
            raise forms.ValidationError(_("رقم الهاتف مستخدم مسبقًا."))
        return phone


class EmailOrPhoneLoginForm(AuthenticationForm):
    username = forms.CharField(
        label=_("اسم المستخدم / البريد / الهاتف"),
        widget=forms.TextInput(attrs={
            "autofocus": True, "placeholder": "username / email / phone",
        }),
    )
    password = forms.CharField(
        label=_("كلمة المرور"), strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ["content", "image", "video"]
        widgets = {
            "content": forms.Textarea(attrs={"rows": 3, "placeholder": _("اكتب فكرة...")})
        }

    def clean_content(self):
        from .profanity import contains_profanity
        content = self.cleaned_data.get("content", "")
        if content and contains_profanity(content):
            raise forms.ValidationError(_("المنشور يحتوي كلمات غير لائقة."))
        return content


class QuoteForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ["content"]
        labels = {"content": _("أضف تعليقك على المنشور")}
        widgets = {"content": forms.Textarea(attrs={"rows": 3})}

    def clean_content(self):
        from .profanity import contains_profanity
        content = self.cleaned_data.get("content", "")
        if content and contains_profanity(content):
            raise forms.ValidationError(_("الاقتباس يحتوي كلمات غير لائقة."))
        return content


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["content"]
        labels = {"content": ""}
        widgets = {"content": forms.Textarea(attrs={"rows": 2, "placeholder": _("اكتب تعليقًا...")})}

    def clean_content(self):
        from .profanity import contains_profanity
        content = self.cleaned_data.get("content", "")
        if content and contains_profanity(content):
            raise forms.ValidationError(_("التعليق يحتوي كلمات غير لائقة."))
        return content


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["reason", "details"]
        labels = {"reason": _("سبب الإبلاغ"), "details": _("تفاصيل إضافية (اختياري)")}
        widgets = {"details": forms.Textarea(attrs={"rows": 3})}


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ["content"]
        labels = {"content": ""}
        widgets = {"content": forms.Textarea(attrs={"rows": 2})}


class ReportMessageForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["reason", "details"]
        labels = {"reason": _("سبب الإبلاغ"), "details": _("تفاصيل إضافية (اختياري)")}
        widgets = {"details": forms.Textarea(attrs={"rows": 3})}


# ==================== إعدادات الملف الشخصي ====================
class ProfileBasicForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["display_name", "avatar", "cover", "bio", "location", "hometown", "website"]
        labels = {
            "display_name": _("الاسم الكامل"),
            "avatar": _("الصورة الشخصية"),
            "cover": _("صورة الغلاف"),
            "bio": _("نبذة عنك"),
            "location": _("المدينة الحالية"),
            "hometown": _("المدينة الأصلية"),
            "website": _("الموقع الإلكتروني"),
        }
        widgets = {
            "display_name": forms.TextInput(attrs={
                "placeholder": _("مثال: علي خالد صالح العنسي"),
                "maxlength": 150,
            }),
            "bio": forms.Textarea(attrs={"rows": 3, "maxlength": 300}),
        }


class ProfilePersonalForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["birthdate", "gender", "relationship_status", "languages"]
        labels = {
            "birthdate": _("تاريخ الميلاد"),
            "gender": _("الجنس"),
            "relationship_status": _("الحالة الاجتماعية"),
            "languages": _("اللغات (مفصولة بفواصل)"),
        }
        widgets = {
            "birthdate": forms.DateInput(attrs={"type": "date"}),
            "languages": forms.TextInput(attrs={"placeholder": _("العربية، الإنجليزية")}),
        }

    def clean_birthdate(self):
        bd = self.cleaned_data.get("birthdate")
        if bd:
            from datetime import date
            today = date.today()
            age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
            if age < 13:
                raise forms.ValidationError(_("يجب أن يكون عمرك 13 عامًا على الأقل."))
            if age > 120:
                raise forms.ValidationError(_("تاريخ الميلاد غير صحيح."))
        return bd


class ProfileWorkForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["education", "job_title", "workplace"]
        labels = {
            "education": _("التعليم (الجامعة / التخصص)"),
            "job_title": _("المسمى الوظيفي"),
            "workplace": _("جهة العمل"),
        }
        widgets = {
            "education": forms.TextInput(attrs={"placeholder": _("جامعة عدن - هندسة حاسوب")}),
            "job_title": forms.TextInput(attrs={"placeholder": _("مهندس برمجيات")}),
            "workplace": forms.TextInput(attrs={"placeholder": _("شركة...")}),
        }


class ProfileInterestsForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["interests"]
        labels = {"interests": _("اهتماماتك")}
        widgets = {
            "interests": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": _("برمجة، رياضة، قراءة، سفر، تصوير..."),
            }),
        }


class PrivacySettingsForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "posts_privacy", "messages_privacy", "friend_requests_privacy",
            "show_email", "show_phone", "show_birthdate", "show_relationship",
            "allow_tagging", "searchable",
        ]
        labels = {
            "posts_privacy": _("من يرى منشوراتي"),
            "messages_privacy": _("من يستطيع مراسلتي"),
            "friend_requests_privacy": _("من يستطيع إرسال طلب صداقة"),
            "show_email": _("إظهار البريد الإلكتروني في ملفي"),
            "show_phone": _("إظهار رقم الهاتف في ملفي"),
            "show_birthdate": _("إظهار تاريخ الميلاد"),
            "show_relationship": _("إظهار الحالة الاجتماعية"),
            "allow_tagging": _("السماح بالإشارة إليّ في المنشورات"),
            "searchable": _("السماح بظهوري في نتائج البحث"),
        }


class NotificationSettingsForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "notify_messages", "notify_followers", "notify_likes",
            "notify_comments", "notify_group_posts", "notify_page_posts",
            "notify_friend_requests", "email_notifications",
        ]
        labels = {
            "notify_messages": _("إشعارات الرسائل الخاصة"),
            "notify_followers": _("عندما يتابعني أحد"),
            "notify_likes": _("عندما يُعجب أحد بمنشوراتي"),
            "notify_comments": _("عندما يعلّق أحد على منشوراتي"),
            "notify_group_posts": _("منشورات جديدة في مجموعاتي"),
            "notify_page_posts": _("منشورات جديدة في الصفحات التي أتابعها"),
            "notify_friend_requests": _("طلبات الصداقة"),
            "email_notifications": _("إرسال إشعارات إلى بريدي الإلكتروني"),
        }


class AppearanceForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["theme_preference"]
        labels = {"theme_preference": _("المظهر الافتراضي")}


class AccountForm(forms.ModelForm):
    email = forms.EmailField(required=True, label=_("البريد الإلكتروني"))
    phone = forms.CharField(
        required=False, max_length=20, label=_("رقم الهاتف"),
        widget=forms.TextInput(attrs={"placeholder": "+967xxxxxxxxx"}),
    )

    class Meta:
        model = User
        fields = ["email"]

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        qs = User.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("هذا البريد مستخدم مسبقًا."))
        return email

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if phone:
            qs = Profile.objects.filter(phone=phone)
            if self.instance.pk and hasattr(self.instance, "profile"):
                qs = qs.exclude(pk=self.instance.profile.pk)
            if qs.exists():
                raise forms.ValidationError(_("رقم الهاتف مستخدم مسبقًا."))
        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            profile = user.profile
            profile.phone = self.cleaned_data.get("phone") or None
            profile.save(update_fields=["phone"])
        return user


class DeleteAccountForm(forms.Form):
    password = forms.CharField(label=_("كلمة المرور"), widget=forms.PasswordInput)
    confirm = forms.CharField(
        label=_("اكتب كلمة: DELETE"),
        widget=forms.TextInput(attrs={"placeholder": "DELETE"}),
    )

    def clean_confirm(self):
        v = self.cleaned_data.get("confirm", "").strip().upper()
        if v != "DELETE":
            raise forms.ValidationError(_("يجب كتابة DELETE بالأحرف الكبيرة."))
        return v


class ChangePasswordForm(forms.Form):
    current = forms.CharField(
        label=_("كلمة المرور الحالية"),
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    new1 = forms.CharField(
        label=_("كلمة المرور الجديدة"),
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        min_length=8,
    )
    new2 = forms.CharField(
        label=_("تأكيد كلمة المرور الجديدة"),
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current(self):
        cur = self.cleaned_data.get("current", "")
        if not self.user.check_password(cur):
            raise forms.ValidationError(_("كلمة المرور الحالية غير صحيحة."))
        return cur

    def clean(self):
        cleaned = super().clean()
        n1 = cleaned.get("new1")
        n2 = cleaned.get("new2")
        if n1 and n2 and n1 != n2:
            self.add_error("new2", _("كلمتا المرور غير متطابقتين."))
        if n1:
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError
            try:
                validate_password(n1, self.user)
            except ValidationError as e:
                self.add_error("new1", e)
        return cleaned

    def save(self):
        self.user.set_password(self.cleaned_data["new1"])
        self.user.save()
        return self.user


# ==================== 2FA ====================
class TwoFAVerifyForm(forms.Form):
    code = forms.CharField(
        max_length=20, min_length=4, label=_("رمز التحقق"),
        widget=forms.TextInput(attrs={
            "autofocus": True, "placeholder": "123456",
            "inputmode": "numeric", "autocomplete": "one-time-code",
        }),
    )


class TwoFAEnableForm(forms.Form):
    code = forms.CharField(
        max_length=6, min_length=6, label=_("أدخل الرمز من التطبيق"),
        widget=forms.TextInput(attrs={
            "placeholder": "000000",
            "inputmode": "numeric", "autocomplete": "one-time-code",
        }),
    )


# ==================== المجموعات والصفحات ====================
class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ["name", "description", "avatar", "cover", "privacy"]
        labels = {
            "name": _("اسم المجموعة"), "description": _("الوصف"),
            "avatar": _("الصورة الرمزية"), "cover": _("صورة الغلاف"), "privacy": _("الخصوصية"),
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        qs = Group.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("اسم المجموعة محجوز."))
        return name


class GroupPostForm(forms.ModelForm):
    class Meta:
        model = GroupPost
        fields = ["content", "image"]
        widgets = {"content": forms.Textarea(attrs={"rows": 3})}

    def clean_content(self):
        from .profanity import contains_profanity
        content = self.cleaned_data.get("content", "")
        if content and contains_profanity(content):
            raise forms.ValidationError(_("المنشور يحتوي كلمات غير لائقة."))
        return content


class PageForm(forms.ModelForm):
    class Meta:
        model = Page
        fields = [
            "name", "category", "description", "avatar", "cover",
            "website", "phone", "address",
        ]
        labels = {
            "name": _("اسم الصفحة"), "category": _("التصنيف"), "description": _("الوصف"),
            "avatar": _("الصورة الرمزية"), "cover": _("صورة الغلاف"),
            "website": _("الموقع الإلكتروني"), "phone": _("الهاتف"), "address": _("العنوان"),
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        qs = Page.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("اسم الصفحة محجوز."))
        return name


class PagePostForm(forms.ModelForm):
    class Meta:
        model = PagePost
        fields = ["content", "image"]
        widgets = {"content": forms.Textarea(attrs={"rows": 3})}

    def clean_content(self):
        from .profanity import contains_profanity
        content = self.cleaned_data.get("content", "")
        if content and contains_profanity(content):
            raise forms.ValidationError(_("المنشور يحتوي كلمات غير لائقة."))
        return content