from django.urls import path
from django.contrib.auth import views as auth_views

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("explore/", views.explore, name="explore"),
    path("signup/", views.signup, name="signup"),
    path("login/", views.SecureLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # ==================== 2FA ====================
    path("2fa/verify/", views.twofa_verify, name="twofa_verify"),
    path("2fa/setup/", views.twofa_setup, name="twofa_setup"),
    path("2fa/enable/", views.twofa_enable, name="twofa_enable"),
    path("2fa/disable/", views.twofa_disable, name="twofa_disable"),
    path("2fa/backup/regenerate/", views.twofa_regenerate_backup, name="twofa_regenerate_backup"),
    path("security/", views.security_settings, name="security_settings"),
    path("security/devices/", views.trusted_devices_list, name="trusted_devices"),
    path("security/devices/<int:pk>/remove/", views.trusted_device_remove, name="trusted_device_remove"),
    path("security/devices/remove-all/", views.trusted_devices_remove_all, name="trusted_devices_remove_all"),
    path("data-export/", views.data_export_preview, name="data_export_preview"),
    path("data-export/download/", views.data_export, name="data_export"),

    path("verify-email/sent/", views.verify_email_sent, name="verify_email_sent"),
    path("verify/<str:token>/", views.verify_email, name="verify_email"),

    path("password-reset/", auth_views.PasswordResetView.as_view(
        template_name="registration/password_reset_form.html",
        email_template_name="registration/password_reset_email.html",
        subject_template_name="registration/password_reset_subject.txt",
        success_url="/password-reset/done/",
    ), name="password_reset"),
    path("password-reset/done/", auth_views.PasswordResetDoneView.as_view(
        template_name="registration/password_reset_done.html",
    ), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="registration/password_reset_confirm.html",
        success_url="/reset/done/",
    ), name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(
        template_name="registration/password_reset_complete.html",
    ), name="password_reset_complete"),

    # ==================== المنشورات ====================
    path("post/new/", views.create_post, name="create_post"),
    path("post/<int:pk>/", views.post_detail, name="post_detail"),
    path("post/<int:pk>/edit/", views.edit_post, name="edit_post"),
    path("post/<int:pk>/delete/", views.delete_post, name="delete_post"),
    path("post/<int:pk>/like/", views.toggle_like, name="toggle_like"),
    path("post/<int:pk>/repost/", views.repost, name="repost"),
    path("post/<int:pk>/quote/", views.quote_post, name="quote_post"),
    path("post/<int:pk>/bookmark/", views.toggle_bookmark, name="toggle_bookmark"),
    path("post/<int:pk>/hide/", views.hide_post, name="hide_post"),
    path("post/<int:pk>/unhide/", views.unhide_post, name="unhide_post"),
    path("post/<int:pk>/report/", views.report_post, name="report_post"),
    path("post-image/<int:pk>/delete/", views.delete_post_image, name="delete_post_image"),

    path("user/<str:username>/hide-all/", views.hide_all_from_user, name="hide_all_from_user"),
    path("user/<str:username>/mute/", views.mute_user, name="mute_user"),
    path("user/<str:username>/unmute/", views.unmute_user, name="unmute_user"),
    path("user/<str:username>/block/", views.block_user, name="block_user"),
    path("user/<str:username>/unblock/", views.unblock_user, name="unblock_user"),

    # ==================== التعليقات ====================
    path("comment/<int:pk>/like/", views.comment_like, name="comment_like"),
    path("comment/<int:pk>/edit/", views.comment_edit, name="comment_edit"),
    path("comment/<int:pk>/delete/", views.comment_delete, name="comment_delete"),

    path("bookmarks/", views.bookmarks_list, name="bookmarks"),

    # ==================== الأصدقاء ====================
    path("friends/", views.friends_list, name="friends"),
    path("friend-requests/", views.friend_requests_list, name="friend_requests"),
    path("friend-request/send/<str:username>/", views.send_friend_request, name="send_friend_request"),
    path("friend-request/accept/<int:pk>/", views.accept_friend_request, name="accept_friend_request"),
    path("friend-request/decline/<int:pk>/", views.decline_friend_request, name="decline_friend_request"),
    path("friend/remove/<str:username>/", views.remove_friend, name="remove_friend"),

    # ==================== المحادثات ====================
    path("chat/", views.chat_list, name="chat_list"),
    path("chat/start/<str:username>/", views.start_chat, name="start_chat"),
    path("chat/<int:pk>/", views.chat_room, name="chat_room"),
    path("chat/<int:pk>/mode/", views.set_conversation_mode, name="set_conversation_mode"),
    path("chat/<int:pk>/disappear/", views.set_disappear, name="set_disappear"),
    path("chat/<int:pk>/delete/", views.delete_conversation, name="delete_conversation"),
    path("chat/<int:pk>/upload/", views.upload_chat_file, name="upload_chat_file"),
    path("chat/message/<int:pk>/report/", views.report_message, name="report_message"),

    # ==================== المجموعات ====================
    path("groups/", views.group_list, name="group_list"),
    path("groups/new/", views.group_create, name="group_create"),
    path("groups/<slug:slug>/", views.group_detail, name="group_detail"),
    path("groups/<slug:slug>/join/", views.group_join, name="group_join"),
    path("groups/<slug:slug>/leave/", views.group_leave, name="group_leave"),
    path("groups/<slug:slug>/members/", views.group_members, name="group_members"),
    path("groups/<slug:slug>/members/remove/<str:username>/", views.group_remove_member, name="group_remove_member"),
    path("groups/<slug:slug>/post/<int:pk>/delete/", views.group_delete_post, name="group_delete_post"),
    path("groups/<slug:slug>/post/<int:pk>/like/", views.group_post_like, name="group_post_like"),

    # ==================== الصفحات ====================
    path("pages/", views.page_list, name="page_list"),
    path("pages/new/", views.page_create, name="page_create"),
    path("pages/<slug:slug>/", views.page_detail, name="page_detail"),
    path("pages/<slug:slug>/edit/", views.page_edit, name="page_edit"),
    path("pages/<slug:slug>/follow/", views.page_follow, name="page_follow"),
    path("pages/<slug:slug>/post/<int:pk>/delete/", views.page_delete_post, name="page_delete_post"),
    path("pages/<slug:slug>/post/<int:pk>/like/", views.page_post_like, name="page_post_like"),

    path("offline/", views.offline, name="offline"),

    # ==================== الإعدادات ====================
    path("settings/", views.settings_index, name="settings_index"),
    path("settings/profile/", views.settings_profile, name="settings_profile"),
    path("settings/personal/", views.settings_personal, name="settings_personal"),
    path("settings/work/", views.settings_work, name="settings_work"),
    path("settings/interests/", views.settings_interests, name="settings_interests"),
    path("settings/privacy/", views.settings_privacy, name="settings_privacy"),
    path("settings/notifications/", views.settings_notifications, name="settings_notifications"),
    path("settings/appearance/", views.settings_appearance, name="settings_appearance"),
    path("settings/account/", views.settings_account, name="settings_account"),
    path("settings/delete/", views.settings_delete_account, name="settings_delete_account"),

    # ==================== الملف الشخصي ====================
    path("profile/edit/", views.edit_profile, name="edit_profile"),
    path("profile/<str:username>/", views.profile_view, name="profile"),
    path("profile/<str:username>/follow/", views.toggle_follow, name="toggle_follow"),

    # ==================== أخرى ====================
    path("search/", views.search, name="search"),
    path("notifications/", views.notifications_list, name="notifications"),
]