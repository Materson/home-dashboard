
import apps.core.crypto
import apps.core.uuid7
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProviderProfile",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=apps.core.uuid7.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=80)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("anthropic", "Anthropic (Claude)"),
                            ("openai", "OpenAI (ChatGPT)"),
                            ("google", "Google (Gemini)"),
                            ("ollama", "Ollama"),
                            ("openai_compatible", "OpenAI-compatible server"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "model",
                    models.CharField(
                        help_text="Model id, e.g. claude-opus-5-5.", max_length=120
                    ),
                ),
                (
                    "base_url",
                    models.CharField(
                        blank=True,
                        help_text="Ollama / self-hosted URL.",
                        max_length=300,
                    ),
                ),
                ("api_key", apps.core.crypto.EncryptedTextField(blank=True)),
                (
                    "location",
                    models.CharField(
                        choices=[
                            ("cloud", "Cloud"),
                            ("local", "Local (on my network)"),
                        ],
                        default="cloud",
                        max_length=5,
                    ),
                ),
                (
                    "vision",
                    models.BooleanField(
                        default=True, help_text="Can read photos and documents."
                    ),
                ),
                ("enabled", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ("name",),
            },
        ),
        migrations.CreateModel(
            name="Conversation",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=apps.core.uuid7.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(blank=True, max_length=120)),
                ("private", models.BooleanField(default=False)),
                ("aliases", models.JSONField(blank=True, default=dict)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="conversations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-updated_at",),
            },
        ),
        migrations.CreateModel(
            name="Message",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=apps.core.uuid7.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "role",
                    models.CharField(
                        choices=[("user", "User"), ("assistant", "Assistant")],
                        max_length=10,
                    ),
                ),
                ("text", models.TextField(blank=True)),
                ("page", models.CharField(blank=True, max_length=200)),
                ("error", models.BooleanField(default=False)),
                (
                    "conversation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        to="assistant.conversation",
                    ),
                ),
            ],
            options={
                "ordering": ("created_at",),
            },
        ),
        migrations.CreateModel(
            name="LLMCall",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=apps.core.uuid7.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("profile_name", models.CharField(max_length=80)),
                ("provider", models.CharField(max_length=20)),
                ("model", models.CharField(max_length=120)),
                ("location", models.CharField(max_length=5)),
                ("modules", models.JSONField(default=list)),
                ("sent", models.JSONField(default=list)),
                ("images", models.PositiveSmallIntegerField(default=0)),
                ("input_tokens", models.PositiveIntegerField(null=True)),
                ("output_tokens", models.PositiveIntegerField(null=True)),
                ("ok", models.BooleanField(default=True)),
                ("error", models.TextField(blank=True)),
                (
                    "conversation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="calls",
                        to="assistant.conversation",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "message",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="calls",
                        to="assistant.message",
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.CreateModel(
            name="PendingAction",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=apps.core.uuid7.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("kind", models.CharField(max_length=40)),
                ("payload", models.JSONField(default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("proposed", "Proposed"),
                            ("done", "Done"),
                            ("cancelled", "Cancelled"),
                            ("undone", "Undone"),
                            ("failed", "Failed"),
                        ],
                        default="proposed",
                        max_length=10,
                    ),
                ),
                ("auto", models.BooleanField(default=False)),
                ("result", models.JSONField(blank=True, default=list)),
                ("error", models.TextField(blank=True)),
                (
                    "conversation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="actions",
                        to="assistant.conversation",
                    ),
                ),
                (
                    "message",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="actions",
                        to="assistant.message",
                    ),
                ),
            ],
            options={
                "ordering": ("created_at",),
            },
        ),
        migrations.CreateModel(
            name="AISettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("policies", models.JSONField(blank=True, default=dict)),
                (
                    "chat_profile",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="assistant.providerprofile",
                    ),
                ),
                (
                    "local_profile",
                    models.ForeignKey(
                        blank=True,
                        help_text="Used for private conversations and local-only modules.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="assistant.providerprofile",
                    ),
                ),
            ],
        ),
    ]
