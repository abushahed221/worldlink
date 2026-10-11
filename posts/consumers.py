import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return

        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        if not await self._is_participant():
            await self.close()
            return

        self.room_group_name = f"chat_{self.conversation_id}"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get("action", "message")

        if action == "typing":
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "typing_event", "sender": self.user.username,
                 "is_typing": data.get("is_typing", False)},
            )
            return

        if action == "read":
            await self._mark_read()
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "read_event", "reader": self.user.username},
            )
            return

        if action == "delete":
            message_id = data.get("message_id")
            if message_id and await self._delete_message(message_id):
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {"type": "delete_event", "message_id": message_id},
                )
            return

        if action == "edit":
            message_id = data.get("message_id")
            new_content = (data.get("content") or "").strip()
            if not message_id or not new_content:
                return
            result = await self._edit_message(message_id, new_content)
            if result:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {"type": "edit_event", "message_id": message_id,
                     "content": new_content, "edited_at": result["edited_at"]},
                )
            return

        if action == "media":
            payload = await self._save_media_message(
                data.get("message_type", "file"),
                data.get("file_url", ""),
                data.get("content", ""),
                data.get("reply_to"),
            )
            if payload:
                await self.channel_layer.group_send(
                    self.room_group_name, {"type": "chat_message", **payload},
                )
            return

        message = (data.get("message") or "").strip()
        if not message:
            return
        payload = await self._save_message(message, data.get("reply_to"))
        await self.channel_layer.group_send(
            self.room_group_name, {"type": "chat_message", **payload},
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    async def typing_event(self, event):
        if event["sender"] == self.user.username:
            return
        await self.send(text_data=json.dumps({
            "type": "typing", "sender": event["sender"],
            "is_typing": event["is_typing"],
        }))

    async def read_event(self, event):
        if event["reader"] == self.user.username:
            return
        await self.send(text_data=json.dumps({"type": "read", "reader": event["reader"]}))

    async def delete_event(self, event):
        await self.send(text_data=json.dumps({
            "type": "delete", "message_id": event["message_id"],
        }))

    async def edit_event(self, event):
        await self.send(text_data=json.dumps({
            "type": "edit", "message_id": event["message_id"],
            "content": event["content"], "edited_at": event["edited_at"],
        }))

    # ============ DB ============
    @database_sync_to_async
    def _is_participant(self):
        from .models import Conversation
        return Conversation.objects.filter(
            id=self.conversation_id, participants=self.user,
        ).exists()

    @database_sync_to_async
    def _mark_read(self):
        from .models import Conversation
        conv = Conversation.objects.get(id=self.conversation_id)
        conv.messages.filter(is_read=False).exclude(sender=self.user).update(is_read=True)

    @database_sync_to_async
    def _delete_message(self, message_id):
        from django.utils import timezone
        from .models import Message
        try:
            m = Message.objects.get(
                id=message_id, conversation_id=self.conversation_id, sender=self.user,
            )
        except Message.DoesNotExist:
            return False
        m.is_deleted = True
        m.deleted_at = timezone.now()
        m.save(update_fields=["is_deleted", "deleted_at"])
        return True

    @database_sync_to_async
    def _edit_message(self, message_id, new_content):
        from django.utils import timezone
        from .crypto import encrypt_text
        from .models import Message
        try:
            m = Message.objects.get(
                id=message_id, conversation_id=self.conversation_id, sender=self.user,
            )
        except Message.DoesNotExist:
            return None
        if m.is_deleted or m.is_media():
            return None
        conv = m.conversation
        stored = encrypt_text(new_content) if conv.mode == "secret" else new_content
        m.content = stored
        m.edited_at = timezone.now()
        m.save(update_fields=["content", "edited_at"])
        return {"edited_at": m.edited_at.strftime("%H:%M")}

    def _build_payload_sync(self, m, decrypted_content):
        reply_data = None
        if m.reply_to:
            from .crypto import decrypt_text
            reply_data = {
                "id": m.reply_to.id,
                "sender": m.reply_to.sender.username,
                "content": decrypt_text(m.reply_to.content)[:80],
            }
        avatar = self.user.profile.avatar.url if self.user.profile.avatar else ""
        file_url = m.file.url if m.file else ""
        return {
            "message_id": m.id, "sender": self.user.username, "sender_id": self.user.id,
            "avatar": avatar, "message_type": m.message_type,
            "content": decrypted_content, "file_url": file_url,
            "file_name": m.file_name(),
            "created_at": m.created_at.strftime("%H:%M"),
            "reply_to": reply_data,
            "edited_at": m.edited_at.strftime("%H:%M") if m.edited_at else "",
        }

    @database_sync_to_async
    def _save_message(self, content, reply_to_id=None):
        from django.utils import timezone
        from .crypto import encrypt_text
        from .models import Conversation, Message, Notification

        conv = Conversation.objects.get(id=self.conversation_id)
        is_secret = conv.mode == "secret"
        stored = encrypt_text(content) if is_secret else content

        reply_obj = None
        if reply_to_id:
            reply_obj = Message.objects.filter(id=reply_to_id, conversation=conv).first()

        m = Message.objects.create(
            conversation=conv, sender=self.user,
            content=stored, message_type="text", reply_to=reply_obj,
        )
        conv.updated_at = timezone.now()
        conv.save(update_fields=["updated_at"])

        for p in conv.participants.exclude(id=self.user.id):
            Notification.objects.create(
                recipient=p, sender=self.user, notification_type="message",
                message="🔒 رسالة سرية" if is_secret else content[:80],
            )
        return self._build_payload_sync(m, content)

    @database_sync_to_async
    def _save_media_message(self, message_type, file_url, content, reply_to_id=None):
        from django.utils import timezone
        from .crypto import encrypt_text
        from .models import Conversation, Message, Notification

        if message_type not in ("image", "video", "audio", "voice", "file"):
            return None

        conv = Conversation.objects.get(id=self.conversation_id)
        is_secret = conv.mode == "secret"
        stored = encrypt_text(content) if (content and is_secret) else (content or "")

        reply_obj = None
        if reply_to_id:
            reply_obj = Message.objects.filter(id=reply_to_id, conversation=conv).first()

        rel_path = file_url.replace("/media/", "", 1) if file_url.startswith("/media/") else file_url

        m = Message.objects.create(
            conversation=conv, sender=self.user,
            content=stored, message_type=message_type,
            file=rel_path, reply_to=reply_obj,
        )
        conv.updated_at = timezone.now()
        conv.save(update_fields=["updated_at"])

        for p in conv.participants.exclude(id=self.user.id):
            Notification.objects.create(
                recipient=p, sender=self.user, notification_type="message",
                message=f"📎 {m.get_message_type_display()}",
            )
        return self._build_payload_sync(m, content or "")


# ==================== الإشعارات الفورية ====================
class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return

        self.group_name = f"notif_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        counts = await self._get_counts()
        await self.send(text_data=json.dumps({"type": "counts", **counts}))

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def user_event(self, event):
        counts = await self._get_counts()
        await self.send(text_data=json.dumps({
            "type": "event",
            "event": event["payload"],
            **counts,
        }))

    @database_sync_to_async
    def _get_counts(self):
        from .models import Friendship, Message
        return {
            "unread_notifications": self.user.notifications.filter(is_read=False).count(),
            "unread_messages": Message.objects.filter(
                conversation__participants=self.user,
                is_read=False, is_deleted=False,
            ).exclude(sender=self.user).count(),
            "pending_requests": Friendship.objects.filter(
                to_user=self.user, status="pending",
            ).count(),
        }