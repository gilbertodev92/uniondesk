from django.db import models
from django.conf import settings

class PasswordAccessLog(models.Model):
    ACTION_CHOICES = [
        ("VIEW", "view"),
        ("CREATE", "create"),
        ("UPDATE", "update"),
        ("DELETE", "delete"),
        ("EXPORT", "export"),
    ]
    credential_id = models.IntegerField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, null=True)
    details = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Log de acesso ao cofre"
        verbose_name_plural = "Logs de acesso ao cofre"
