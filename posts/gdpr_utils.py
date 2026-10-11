"""
تنزيل بيانات المستخدم — GDPR compliance.
يجمع كل بيانات المستخدم في قاموس ثم يُصدّرها كـ JSON.
"""

import json
from datetime import date, datetime
from decimal import Decimal

from django.utils import timezone


def _serialize(obj):
    """تحويل الكائنات إلى JSON-friendly."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if hasattr(obj, "url"):
        return obj.url
    return str(obj)


def build_user_data(user):
    """
    يبني قاموسًا يحتوي كل بيانات المستخدم.
    """
    from .models import (
        Profile, Post, PostImage, Comment, Notification, Friendship,
        UserRelation, Bookmark, HiddenPost, Report, Conversation, Message,
        Group, GroupMember, GroupPost, Page, PageFollower, PagePost,
        LoginAttempt, TrustedDevice,
    )

    data = {
        "export_meta": {
            "generated_at": timezone.now().isoformat(),
            "format_version": "1.0",
            "user": user.username,
            "note": "This is a full export of your WorldLink data.",
        },
        "account": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
            "date_joined": user.date_joined.isoformat(),
            "last_login": user.last_login.isoformat() if user.last_login else None,
        },
        "profile": {},
        "posts": [],
        "comments": [],
        "likes_given": [],
        "bookmarks": [],
        "friends": {
            "friends": [],
            "sent_requests": [],
            "received_requests": [],
        },
        "follows": {
            "following": [],
            "followers": [],
        },
        "relations": {
            "muted": [],
            "blocked": [],
        },
        "conversations": [],
        "groups": {
            "memberships": [],
            "created_groups": [],
            "group_posts": [],
        },
        "pages": {
            "followed_pages": [],
            "owned_pages": [],
            "page_posts": [],
        },
        "notifications_sent": [],
        "reports_made": [],
        "sessions": [],
        "trusted_devices": [],
        "login_attempts": [],
    }

    # ==================== Profile ====================
    try:
        p = user.profile
        data["profile"] = {
            "display_name": p.display_name,
            "bio": p.bio,
            "location": p.location,
            "hometown": p.hometown,
            "website": p.website,
            "phone": p.phone,
            "birthdate": p.birthdate.isoformat() if p.birthdate else None,
            "gender": p.gender,
            "relationship_status": p.relationship_status,
            "languages": p.languages,
            "education": p.education,
            "job_title": p.job_title,
            "workplace": p.workplace,
            "interests": p.interests,
            "is_verified": p.is_verified,
            "is_2fa_enabled": p.is_2fa_enabled,
            "created_at": p.created_at.isoformat(),
        }
    except Profile.DoesNotExist:
        pass

    # ==================== Posts ====================
    for post in Post.objects.filter(author=user).prefetch_related("images"):
        data["posts"].append({
            "id": post.id,
            "content": post.content,
            "image": post.image.url if post.image else None,
            "video": post.video.url if post.video else None,
            "images": [img.image.url for img in post.images.all()],
            "is_quote": post.is_quote,
            "created_at": post.created_at.isoformat(),
            "updated_at": post.updated_at.isoformat(),
        })

    # ==================== Comments ====================
    for c in Comment.objects.filter(author=user).select_related("post"):
        data["comments"].append({
            "id": c.id,
            "post_id": c.post_id,
            "parent_id": c.parent_id,
            "content": c.content,
            "created_at": c.created_at.isoformat(),
        })

    # ==================== Likes given ====================
    for post in Post.objects.filter(likes=user):
        data["likes_given"].append({
            "type": "post",
            "post_id": post.id,
            "author": post.author.username,
        })

    # ==================== Bookmarks ====================
    for bm in Bookmark.objects.filter(user=user).select_related("post"):
        data["bookmarks"].append({
            "post_id": bm.post_id,
            "created_at": bm.created_at.isoformat(),
        })

    # ==================== Friends ====================
    sent = Friendship.objects.filter(from_user=user, status="accepted")
    received = Friendship.objects.filter(to_user=user, status="accepted")
    for f in sent:
        data["friends"]["friends"].append(f.to_user.username)
    for f in received:
        if f.from_user.username not in data["friends"]["friends"]:
            data["friends"]["friends"].append(f.from_user.username)

    for f in Friendship.objects.filter(from_user=user, status="pending"):
        data["friends"]["sent_requests"].append(f.to_user.username)
    for f in Friendship.objects.filter(to_user=user, status="pending"):
        data["friends"]["received_requests"].append(f.from_user.username)

    # ==================== Follows ====================
    for prof in user.profile.following.all():
        data["follows"]["following"].append(prof.user.username)
    for prof in user.profile.followers.all():
        data["follows"]["followers"].append(prof.user.username)

    # ==================== Relations ====================
    for r in UserRelation.objects.filter(user=user):
        if r.relation_type == "mute":
            data["relations"]["muted"].append(r.target.username)
        else:
            data["relations"]["blocked"].append(r.target.username)

    # ==================== Conversations ====================
    from .crypto import decrypt_text
    for conv in user.conversations.all():
        msgs = []
        for m in conv.messages.filter(sender=user, is_deleted=False):
            msgs.append({
                "content": decrypt_text(m.content) if conv.is_secret() else m.content,
                "type": m.message_type,
                "sent_at": m.created_at.isoformat(),
            })
        if msgs:
            other = conv.other_participant(user)
            data["conversations"].append({
                "with": other.username if other else "—",
                "mode": conv.mode,
                "messages": msgs,
            })

    # ==================== Groups ====================
    for gm in GroupMember.objects.filter(user=user).select_related("group"):
        data["groups"]["memberships"].append({
            "group": gm.group.name,
            "role": gm.role,
            "joined_at": gm.joined_at.isoformat(),
        })

    for g in Group.objects.filter(creator=user):
        data["groups"]["created_groups"].append({
            "name": g.name,
            "created_at": g.created_at.isoformat(),
        })

    for gp in GroupPost.objects.filter(author=user).select_related("group"):
        data["groups"]["group_posts"].append({
            "group": gp.group.name,
            "content": gp.content,
            "created_at": gp.created_at.isoformat(),
        })

    # ==================== Pages ====================
    for pf in PageFollower.objects.filter(user=user).select_related("page"):
        data["pages"]["followed_pages"].append({
            "page": pf.page.name,
            "followed_at": pf.followed_at.isoformat(),
        })

    for pg in Page.objects.filter(owner=user):
        data["pages"]["owned_pages"].append({
            "name": pg.name,
            "created_at": pg.created_at.isoformat(),
        })

    for pp in PagePost.objects.filter(author=user).select_related("page"):
        data["pages"]["page_posts"].append({
            "page": pp.page.name,
            "content": pp.content,
            "created_at": pp.created_at.isoformat(),
        })

    # ==================== Notifications sent ====================
    for n in Notification.objects.filter(sender=user)[:500]:
        data["notifications_sent"].append({
            "to": n.recipient.username,
            "type": n.notification_type,
            "created_at": n.created_at.isoformat(),
        })

    # ==================== Reports made ====================
    for r in Report.objects.filter(reporter=user):
        data["reports_made"].append({
            "reason": r.reason,
            "created_at": r.created_at.isoformat(),
        })

    # ==================== Sessions ====================
    for s in user.active_sessions.all()[:100]:
        data["sessions"].append({
            "ip": s.ip_address,
            "device": s.device_type,
            "browser": s.browser,
            "os": s.os,
            "last_activity": s.last_activity.isoformat(),
        })

    # ==================== Trusted devices ====================
    for d in TrustedDevice.objects.filter(user=user):
        data["trusted_devices"].append({
            "name": d.device_name,
            "ip": d.ip_address,
            "expires_at": d.expires_at.isoformat(),
        })

    # ==================== Login attempts ====================
    for a in LoginAttempt.objects.filter(username__iexact=user.username)[:100]:
        data["login_attempts"].append({
            "success": a.success,
            "ip": a.ip_address,
            "created_at": a.created_at.isoformat(),
        })

    return data


def to_json_bytes(data):
    """تحويل البيانات إلى JSON bytes بأكواد UTF-8."""
    return json.dumps(data, ensure_ascii=False, indent=2, default=_serialize).encode("utf-8")