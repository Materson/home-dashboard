"""Custom user keyed on email (no username), and one-time password links."""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStamped, UUIDModel


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create(self, email: str, password: str | None, **extra) -> "User":
        if not email:
            raise ValueError("email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra) -> "User":
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra) -> "User":
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self._create(email, password, **extra)


class User(AbstractUser):
    """Email login, no username."""

    username = None  # type: ignore[assignment]
    email = models.EmailField(_("email address"), unique=True)
    locale = models.CharField(max_length=5, default="en", choices=[("en", "English"), ("pl", "Polski")])

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    def __str__(self) -> str:
        return self.email


class PasswordLink(UUIDModel, TimeStamped):
    """A one-time link to set a password: an invite for a new account (made
    by an admin, no password yet) or a reset. Only the token's SHA-256 is
    stored; the link is shown once, to the admin who made it."""

    class Purpose(models.TextChoices):
        INVITE = "invite", "Invite"
        RESET = "reset", "Reset"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="password_links"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    purpose = models.CharField(max_length=6, choices=Purpose.choices)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    def __str__(self) -> str:
        return f"{self.purpose} for {self.user}"
