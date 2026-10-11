from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Notification, Message


def _push_update(user_id, payload):
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(
            f"notif_{user_id}",
            {"type": "user_event", "payload": payload},
        )
    except Exception:
        pass


@receiver(post_save, sender=Notification)
def on_notification_created(sender, instance, created, **kwargs):
    if not created:
        return
    _push_update(instance.recipient_id, {
        "kind": "notification",
        "notification_type": instance.notification_type,
        "sender": instance.sender.username if instance.sender else "",
        "message": (instance.message or "")[:120],
        "notification_id": instance.id,
    })


@receiver(post_save, sender=Message)
def on_message_created(sender, instance, created, **kwargs):
    if not created:
        return
    conv = instance.conversation
    preview = "🔒 رسالة سرية" if conv.is_secret() else (
        instance.content[:80] if instance.content else "📎 مرفق"
    )
    for p in conv.participants.exclude(id=instance.sender_id):
        _push_update(p.id, {
            "kind": "message",
            "sender": instance.sender.username,
            "conversation_id": conv.id,
            "preview": preview,
        })