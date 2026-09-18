# cofre_senhas/models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import os
import base64
from .utils.crypto import encrypt_text, decrypt_text

User = get_user_model()


def make_salt():
    # sempre devolve bytes
    return base64.urlsafe_b64encode(os.urandom(12))


class _CryptoMixin:
    """
    Reúne a lógica de cripto usada por Credential e CredentialAccount.
    Espera que a classe tenha `salt` e os campos binários correspondentes.
    """

    @staticmethod
    def _to_cipher_str(raw):
        if not raw:
            return None
        if isinstance(raw, memoryview):
            raw = raw.tobytes()
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        return str(raw)

    def _encrypt(self, plaintext: str):
        if not self.salt:
            self.salt = make_salt()
        return encrypt_text(plaintext, record_salt=self.salt).encode("utf-8")

    def _decrypt(self, raw) -> str:
        cipher_str = self._to_cipher_str(raw)
        if not cipher_str:
            return ""
        try:
            return decrypt_text(cipher_str, record_salt=self.salt)
        except Exception:
            return ""


class Credential(_CryptoMixin, models.Model):
    """
    Uma ENTRADA do cofre. Pode ser:
      - um acesso único (senha direto aqui), ou
      - um agrupador de vários acessos (ver CredentialAccount).
    """
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="cofre_credentials"
    )
    title = models.CharField("Título", max_length=200)
    username = models.CharField("Usuário / Login", max_length=200, blank=True, null=True)

    encrypted_password = models.BinaryField(blank=True, null=True)
    encrypted_notes = models.BinaryField(blank=True, null=True)

    salt = models.BinaryField(max_length=32)

    tags = models.CharField("Tags", max_length=200, blank=True, null=True)
    is_favorite = models.BooleanField(default=False)
    last_accessed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Credencial"
        verbose_name_plural = "Credenciais"
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.salt:
            self.salt = make_salt()
        super().save(*args, **kwargs)

    # -------------------------------------------------
    # SENHA
    # -------------------------------------------------
    def set_password(self, plaintext: str):
        if plaintext is None:
            self.encrypted_password = b""
            return
        self.encrypted_password = self._encrypt(plaintext)

    def get_password(self) -> str:
        """
        Descriptografa e devolve str.

        NOTA: não registra acesso aqui de propósito. Leitura não deve
        ter efeito colateral de escrita — quem revela chama touch_access().
        """
        return self._decrypt(self.encrypted_password)

    def touch_access(self):
        """Marca acesso sem disparar save() completo (evita reentrância)."""
        agora = timezone.now()
        Credential.objects.filter(pk=self.pk).update(last_accessed_at=agora)
        self.last_accessed_at = agora

    # -------------------------------------------------
    # ANOTAÇÕES
    # -------------------------------------------------
    def set_notes(self, plaintext: str):
        # string vazia LIMPA as notas (antes era impossível apagar)
        if not plaintext:
            self.encrypted_notes = None
            return
        self.encrypted_notes = self._encrypt(plaintext)

    def get_notes(self) -> str:
        return self._decrypt(self.encrypted_notes)

    # -------------------------------------------------
    @property
    def is_multi(self) -> bool:
        """True quando a entrada agrupa vários acessos."""
        return self.accounts.exists()

    @property
    def accounts_count(self) -> int:
        return self.accounts.count()

    def mask_password(self):
        return "••••••••"


class CredentialAccount(_CryptoMixin, models.Model):
    """
    Um acesso individual dentro de uma Credential.

    Resolve o caso "um serviço, vários clientes": antes isso era
    despejado no campo de notas em texto plano, sem busca, sem cópia,
    sem auditoria individual e revelando tudo de uma vez.

    Cada acesso tem seu PRÓPRIO salt e sua própria cifra.
    """
    credential = models.ForeignKey(
        Credential,
        on_delete=models.CASCADE,
        related_name="accounts",
        verbose_name="Credencial",
    )

    label = models.CharField(
        "Identificação",
        max_length=200,
        help_text="Nome do cliente/ambiente (ex.: Mercado Feller).",
    )

    # Se você tiver o app de clientes, descomente e ajuste o label do app.
    # Vincular ao cadastro evita divergência de nome e habilita busca cruzada.
    # cliente = models.ForeignKey(
    #     "clientes.Cliente", null=True, blank=True,
    #     on_delete=models.SET_NULL, related_name="credenciais_cofre",
    # )

    username = models.CharField("Usuário / Login", max_length=200, blank=True, null=True)

    encrypted_password = models.BinaryField(blank=True, null=True)
    encrypted_notes = models.BinaryField(blank=True, null=True)

    salt = models.BinaryField(max_length=32)

    order = models.PositiveIntegerField("Ordem", default=0)
    last_accessed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Acesso da credencial"
        verbose_name_plural = "Acessos da credencial"
        ordering = ["order", "label"]
        indexes = [
            models.Index(fields=["credential", "order"]),
        ]

    def __str__(self):
        return f"{self.credential.title} — {self.label}"

    def save(self, *args, **kwargs):
        if not self.salt:
            self.salt = make_salt()
        super().save(*args, **kwargs)

    def set_password(self, plaintext: str):
        if plaintext is None:
            self.encrypted_password = b""
            return
        self.encrypted_password = self._encrypt(plaintext)

    def get_password(self) -> str:
        return self._decrypt(self.encrypted_password)

    def set_notes(self, plaintext: str):
        if not plaintext:
            self.encrypted_notes = None
            return
        self.encrypted_notes = self._encrypt(plaintext)

    def get_notes(self) -> str:
        return self._decrypt(self.encrypted_notes)

    def touch_access(self):
        agora = timezone.now()
        CredentialAccount.objects.filter(pk=self.pk).update(last_accessed_at=agora)
        self.last_accessed_at = agora

    def mask_password(self):
        return "••••••••"