from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.db.models import Q


class EmailOrPhoneBackend(ModelBackend):
    """يتيح الدخول باسم المستخدم أو البريد أو الهاتف."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get("username")
        if username is None or password is None:
            return None
        try:
            user = User.objects.get(
                Q(username__iexact=username) |
                Q(email__iexact=username) |
                Q(profile__phone=username)
            )
        except User.DoesNotExist:
            User().set_password(password)
            return None
        except User.MultipleObjectsReturned:
            user = User.objects.filter(
                Q(username__iexact=username) | Q(email__iexact=username)
            ).first()
            if not user:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None