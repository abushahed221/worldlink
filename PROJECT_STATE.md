# WorldLink — وثيقة المشروع الرسمية
آخر تحديث: 2026-10-11

---

## 🎯 ما هو المشروع
شبكة تواصل اجتماعي عربية، مبنية بـ Django + Daphne + SQLite،
تعمل محليًا على Windows في: D:\WorldLink

---

## 💻 البيئة

### المسارات
- المشروع: D:\WorldLink
- البيئة الافتراضية: D:\WorldLink\.venv
- قاعدة البيانات: D:\WorldLink\db.sqlite3
- ملفات المستخدمين: D:\WorldLink\media\
- الملفات الثابتة: D:\WorldLink\static\
- ملفات الترجمة: D:\WorldLink\locale\
- النسخ الاحتياطية: D:\WorldLink\backups\
- السجلات: D:\WorldLink\security.log
- gettext: C:\gettext\bin

### التقنيات
- Python 3.13
- Django 5.2
- Daphne 4.x (ASGI)
- Channels 4.x (WebSocket)
- SQLite
- cryptography, pyotp, qrcode, Pillow, python-dotenv

### المكتبات المثبتة
pip install:
- Django>=5.2,<5.3
- channels>=4.0
- daphne>=4.0
- cryptography>=42.0
- Pillow>=10.0
- pyotp>=2.9
- qrcode[pil]>=7.4
- python-dotenv>=1.0
- sentry-sdk[django]>=2.0

---

## 🗂️ هيكل المجلدات

D:\WorldLink\
├── .venv\                          (البيئة الافتراضية)
├── .env                            (أسرار المشروع — لا يُرفع)
├── .gitignore
├── manage.py
├── db.sqlite3
├── security.log
├── backups\
├── locale\
│   └── en\LC_MESSAGES\
│       ├── django.po
│       └── django.mo
├── static\
│   ├── manifest.json
│   ├── sw.js                       (Service Worker)
│   ├── icon.svg
│   └── version.json
├── media\
│   ├── avatars\
│   ├── covers\
│   ├── posts\
│   ├── chat\files\
│   ├── groups\
│   └── pages\
├── config\                         (إعدادات Django)
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
└── posts\                          (التطبيق الرئيسي)
    ├── __init__.py
    ├── admin.py
    ├── apps.py
    ├── backends.py                 (EmailOrPhoneBackend)
    ├── consumers.py                (Chat + Notifications WebSocket)
    ├── context_processors.py
    ├── crypto.py                   (AES Fernet للمحادثات السرية)
    ├── forms.py
    ├── middleware.py               (Rate limit + Security + Admin)
    ├── models.py
    ├── profanity.py                (فلتر الكلمات المسيئة)
    ├── routing.py
    ├── security_utils.py           (كشف الحسابات المزيفة)
    ├── signals.py                  (Profile creation)
    ├── signals_admin.py            (سجل الأدمن)
    ├── signals_notifications.py    (إشعارات فورية)
    ├── signals_security.py         (كشف الحسابات المزيفة)
    ├── urls.py
    ├── views.py
    ├── management\
    │   └── commands\
    │       └── backup_db.py
    └── templates\posts\
        ├── base.html
        ├── home.html
        ├── explore.html
        ├── profile.html
        ├── search.html
        ├── notifications.html
        ├── bookmarks.html
        ├── friends.html
        ├── friend_requests.html
        ├── create_post.html
        ├── edit_post.html
        ├── delete_post.html
        ├── post_detail.html
        ├── _post_card.html
        ├── _comment.html
        ├── _media.html
        ├── quote_post.html
        ├── report_post.html
        ├── report_message.html
        ├── comment_edit.html
        ├── chat_list.html
        ├── chat_room.html
        ├── group_list.html
        ├── group_detail.html
        ├── group_create.html
        ├── group_members.html
        ├── page_list.html
        ├── page_detail.html
        ├── page_create.html
        ├── login.html
        ├── login_2fa.html
        ├── setup_2fa.html
        ├── setup_2fa_success.html
        ├── security_settings.html
        ├── signup.html
        ├── verify_email_sent.html
        ├── verify_email_invalid.html
        ├── offline.html
        ├── ratelimited.html
        ├── settings\
        │   ├── _base.html
        │   ├── index.html
        │   ├── profile.html
        │   ├── personal.html
        │   ├── work.html
        │   ├── interests.html
        │   ├── privacy.html
        │   ├── notifications.html
        │   ├── appearance.html
        │   ├── account.html
        │   └── delete_account.html
        └── registration\
            ├── password_reset_form.html
            ├── password_reset_done.html
            ├── password_reset_confirm.html
            ├── password_reset_complete.html
            ├── password_reset_email.html
            └── password_reset_subject.txt

---

## 🗄️ قاعدة البيانات — النماذج

### Profile
- user (OneToOne)
- display_name (الاسم العربي الكامل)
- bio, avatar, cover, location, hometown, website, phone
- birthdate, gender, relationship_status, languages
- education, job_title, workplace, interests
- following (M2M → self)
- is_verified, verification_token
- is_suspended, suspended_until, suspension_reason, warning_count
- is_2fa_enabled, totp_secret, backup_codes, last_2fa_verified
- posts_privacy, messages_privacy, friend_requests_privacy
- show_email, show_phone, show_birthdate, show_relationship
- allow_tagging, searchable
- notify_messages, notify_followers, notify_likes, notify_comments
- notify_group_posts, notify_page_posts, notify_friend_requests
- email_notifications
- theme_preference
- created_at, updated_at

### Post
- author (FK User), content, image, video, repost_of (FK self)
- is_quote, is_hidden_by_admin, hidden_reason
- likes (M2M User)
- created_at, updated_at

### PostImage
- post (FK), image, created_at

### Comment
- post (FK), author (FK), parent (FK self)
- content, likes (M2M)
- created_at, updated_at

### Notification
- recipient, sender, notification_type (15 نوع)
- post, comment, message
- is_read, created_at

### Friendship
- from_user, to_user, status (pending/accepted/declined)
- created_at

### UserRelation
- user, target, relation_type (mute/block)

### LoginAttempt
- username, ip_address, success, created_at

### Bookmark
- user, post, created_at

### HiddenPost
- user, post, created_at

### Report
- reporter, post, reported_user, message
- reason (6 أنواع), details, is_reviewed
- created_at

### Conversation
- participants (M2M User)
- mode (normal/secret)
- disappear_after (0/300/3600/86400/604800)
- created_at, updated_at

### Message
- conversation, sender, content
- message_type (text/image/video/audio/voice/file)
- file, reply_to (FK self)
- is_read, is_deleted, deleted_at, edited_at
- created_at

### Group
- name, slug, description, avatar, cover
- creator, privacy (public/private)
- is_hidden_by_admin, created_at

### GroupMember
- group, user, role (admin/moderator/member), joined_at

### GroupPost
- group, author, content, image, likes (M2M), created_at

### Page
- name, slug, category (7 أنواع), description
- avatar, cover, owner
- website, phone, address
- is_hidden_by_admin, created_at

### PageFollower
- page, user, followed_at

### PagePost
- page, author, content, image, likes (M2M), created_at

### AdminLog
- user, username_tried, action (9 أنواع)
- target_model, target_id, details
- ip_address, user_agent, path
- created_at

### UserSession
- user, session_key, ip_address, user_agent
- device_type, browser, os
- country, city
- is_current, last_activity, created_at

### SuspiciousAccount
- user, level (low/medium/high/critical)
- status (pending/cleared/blocked)
- reason, signals (JSON), ip_address, user_agent
- reviewed_by, reviewed_at, notes
- created_at

---

## 🔗 الروابط الأساسية

### الحساب
- /signup/                    التسجيل
- /login/                     الدخول
- /logout/                    الخروج
- /verify/<token>/            تفعيل البريد
- /password-reset/            استرجاع كلمة المرور
- /2fa/verify/                التحقق بخطوتين
- /2fa/setup/                 إعداد 2FA
- /2fa/enable/                تفعيل 2FA
- /2fa/disable/               تعطيل 2FA
- /security/                  الإعدادات الأمنية

### المحتوى
- /                           الرئيسية
- /explore/                   استكشاف
- /post/new/                  منشور جديد
- /post/<id>/                 تفاصيل منشور
- /post/<id>/edit/            تعديل
- /post/<id>/delete/          حذف
- /post/<id>/like/            إعجاب
- /post/<id>/repost/          إعادة نشر
- /post/<id>/quote/           اقتباس
- /post/<id>/bookmark/        حفظ
- /post/<id>/hide/            إخفاء
- /post/<id>/report/          إبلاغ
- /bookmarks/                 المحفوظات

### التفاعل
- /comment/<id>/like/         إعجاب بتعليق
- /comment/<id>/edit/         تعديل تعليق
- /comment/<id>/delete/       حذف تعليق

### الأصدقاء
- /friends/                   قائمة الأصدقاء
- /friend-requests/           طلبات الصداقة
- /friend-request/send/<u>/   إرسال طلب
- /friend-request/accept/<id>/ قبول
- /friend-request/decline/<id>/ رفض
- /friend/remove/<u>/         إزالة صديق

### الملف الشخصي
- /profile/<username>/        عرض الملف
- /profile/<username>/follow/ متابعة
- /profile/edit/              → يوجه للإعدادات

### المحادثات
- /chat/                      قائمة المحادثات
- /chat/start/<u>/            بدء محادثة
- /chat/<id>/                 غرفة محادثة
- /chat/<id>/mode/            وضع (عادي/سري)
- /chat/<id>/disappear/       وقت الاختفاء
- /chat/<id>/delete/          حذف محادثة
- /chat/<id>/upload/          رفع ملف
- /chat/message/<id>/report/  إبلاغ عن رسالة

### WebSocket
- /ws/chat/<conversation_id>/  محادثة فورية
- /ws/notifications/           إشعارات فورية

### المجموعات
- /groups/                    قائمة
- /groups/new/                إنشاء
- /groups/<slug>/            عرض
- /groups/<slug>/join/       انضمام
- /groups/<slug>/leave/      مغادرة
- /groups/<slug>/members/    الأعضاء
- /groups/<slug>/members/remove/<u>/ إزالة
- /groups/<slug>/post/<id>/delete/ حذف منشور
- /groups/<slug>/post/<id>/like/ إعجاب

### الصفحات
- /pages/                     قائمة
- /pages/new/                 إنشاء
- /pages/<slug>/             عرض
- /pages/<slug>/edit/        تعديل
- /pages/<slug>/follow/      متابعة
- /pages/<slug>/post/<id>/delete/ حذف منشور
- /pages/<slug>/post/<id>/like/ إعجاب

### الإعدادات
- /settings/                  نظرة عامة
- /settings/profile/          الاسم والصورة والغلاف
- /settings/personal/         شخصي
- /settings/work/             العمل
- /settings/interests/        اهتمامات
- /settings/privacy/          خصوصية
- /settings/notifications/    إشعارات
- /settings/appearance/       مظهر
- /settings/account/          الحساب
- /settings/delete/           حذف الحساب

### أخرى
- /search/?q=...              بحث
- /notifications/             إشعارات
- /offline/                   صفحة بدون اتصال
- /i18n/setlang/              تغيير اللغة

### الأدمن
- /wl-panel-x7k9m2/           لوحة الإدارة (مخفي)
  (محمي بـ IP + 2FA إجباري)
- /admin/                     404

---

## 🔐 الأمان

### الحمايات المفعّلة
- Rate Limiting: 120 req/min عام، 30 login/min، 10 signup/min
- HTTPS إجباري (في الإنتاج)
- HSTS (في الإنتاج)
- X-Frame-Options: DENY
- CSRF
- Suspicious paths blocked
- Admin hidden URL + IP whitelist + 2FA
- 2FA (TOTP + 8 أكواد احتياطية)
- فلتر كلمات مسيئة (عربي + إنجليزي)
- كشف الحسابات المزيفة (تلقائي عند التسجيل)
- كشف البريد المؤقت
- كشف أسماء مشبوهة
- تشفير AES للمحادثات السرية
- نسخ احتياطي يدوي (backup_db command)

### الميدل وير بالترتيب
1. SecurityMiddleware
2. SessionMiddleware
3. LocaleMiddleware
4. CommonMiddleware
5. CsrfViewMiddleware
6. AuthenticationMiddleware
7. MessageMiddleware
8. XFrameOptionsMiddleware
9. SessionTrackingMiddleware (جديد)
10. RateLimitMiddleware
11. SecurityHeadersMiddleware
12. SuspiciousActivityMiddleware
13. AdminSecurityMiddleware

---

## 🚀 أوامر التشغيل اليومية

### كل يوم
```powershell
cd D:\WorldLink
.\.venv\Scripts\python.exe manage.py runserver

احفظ الملف.

---

## 📄 الخطوة 2: ملاحظتك عن 2FA

**صحيح تمامًا** — 2FA في كل تسجيل دخول **مزعج**. هذا حل مشكلة حقيقية.

**الحل المعياري (تستخدمه Google، Facebook، GitHub):**

> عند نجاح 2FA، السيرفر يعطيك **كوكي** صالح 30 يومًا.  
> في الدخول التالي، لو الكوكي موجود → **يتخطى 2FA**.  
> المستخدم يرى قائمة بالأجهزة الموثوقة في `/security/` ويستطيع حذف أي منها.

**سأنفذه في الرد التالي.**

---

## ✅ ما تحتاجه الآن

**1)** احفظ ملف `PROJECT_STATE.md` في `D:\WorldLink\`

**2)** أخبرني:

**A** — حفظت الوثيقة → أرسل الرد التالي (2FA Remember Device)  
**B** — لدي سؤال عن الوثيقة → اسأل

**ثم نكمل بالرد التالي.**