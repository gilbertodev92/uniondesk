from django.contrib import admin
from .models import Credential
from .models_audit import PasswordAccessLog

@admin.register(Credential)
class CredentialAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "owner", "tags", "is_favorite", "last_accessed_at")
    readonly_fields = ("encrypted_password", "encrypted_notes", "salt")
    search_fields = ("title", "owner__username", "tags")

@admin.register(PasswordAccessLog)
class PasswordAccessLogAdmin(admin.ModelAdmin):
    list_display = ("credential_id", "user", "action", "timestamp", "ip_address")
    readonly_fields = [f.name for f in PasswordAccessLog._meta.fields]
    search_fields = ("user__username", "action")
