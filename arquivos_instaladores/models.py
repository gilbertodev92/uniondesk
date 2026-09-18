import hashlib
import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.text import slugify

User = get_user_model()


class CategoriaChoices(models.TextChoices):
    INSTALADORES = "instaladores", "Instaladores"
    ATUALIZACOES = "atualizacoes", "Atualizações"
    UTILITARIOS = "utilitarios", "Utilitários"
    DRIVER_IMPRESSAO = "driver-impressao", "Driver Impressão"
    BALANCAS = "balancas", "Balanças"
    SCRIPTS = "scripts", "Scripts"
    DOCUMENTOS = "documentos", "Documentos"
    CERTIFICADOS = "certificados", "Certificados"


# Ícone Font Awesome por categoria — usado no card no lugar do ícone fixo.
CATEGORIA_ICONE = {
    "instaladores": "fa-box-archive",
    "atualizacoes": "fa-rotate",
    "utilitarios": "fa-screwdriver-wrench",
    "driver-impressao": "fa-print",
    "balancas": "fa-scale-balanced",
    "scripts": "fa-terminal",
    "documentos": "fa-file-lines",
    "certificados": "fa-certificate",
}


def upload_to_categoria(instance, filename):
    categoria = instance.categoria or "outros"
    base, ext = os.path.splitext(filename)
    safe_base = slugify(base)[:80] or "arquivo"
    return f"arquivos_instaladores/{categoria}/{safe_base}{ext.lower()}"


class ArquivoItem(models.Model):
    titulo = models.CharField("Título", max_length=180)
    categoria = models.CharField(
        "Categoria", max_length=32, choices=CategoriaChoices.choices, db_index=True
    )
    versao = models.CharField("Versão", max_length=40, blank=True)
    descricao = models.TextField("Descrição", blank=True)

    arquivo = models.FileField(
        "Arquivo", upload_to=upload_to_categoria, blank=True, null=True, max_length=255
    )
    link_externo = models.URLField("Link externo (opcional)", blank=True)

    tamanho_bytes = models.PositiveBigIntegerField("Tamanho (bytes)", default=0, editable=False)
    checksum_sha256 = models.CharField("SHA256", max_length=64, blank=True, editable=False)

    # NOVO: contador de downloads. Antes não existia — não dava para saber
    # qual instalador a equipe realmente usa.
    downloads = models.PositiveIntegerField("Downloads", default=0, editable=False)

    is_ativo = models.BooleanField("Ativo", default=True)
    criado_por = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploads"
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-criado_em",)
        verbose_name = "Arquivo / Instalador"
        verbose_name_plural = "Arquivos e Instaladores"
        indexes = [
            models.Index(fields=["categoria", "-criado_em"]),
            models.Index(fields=["is_ativo"]),
        ]

    def __str__(self):
        return f"{self.titulo} ({self.get_categoria_display()})"

    # --- Metadados ---
    # NOTA: NÃO calculamos mais o SHA256 dentro do save(). Para um arquivo de
    # 1GB, ler tudo no request síncrono estoura o timeout do gunicorn e
    # derruba o upload. O checksum é calculado depois, fora do request
    # (ver views.finalizar_upload, em streaming), e gravado com update().
    def calcular_sha256_streaming(self):
        """Lê em blocos de 4MB — nunca carrega o arquivo inteiro na RAM."""
        if not self.arquivo:
            return ""
        hasher = hashlib.sha256()
        with self.arquivo.open("rb") as f:
            for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @property
    def filename(self):
        return os.path.basename(self.arquivo.name) if self.arquivo else ""

    @property
    def extensao(self):
        _, ext = os.path.splitext(self.filename)
        return ext.lstrip(".").lower()

    @property
    def icone(self):
        return CATEGORIA_ICONE.get(self.categoria, "fa-file")

    @property
    def tem_arquivo_local(self):
        return bool(self.arquivo)

    @property
    def tamanho_legivel(self):
        n = self.tamanho_bytes or 0
        for unidade in ["B", "KB", "MB", "GB", "TB"]:
            if n < 1024:
                return f"{n:.0f} {unidade}" if unidade in ("B", "KB") else f"{n:.1f} {unidade}"
            n /= 1024
        return f"{n:.1f} PB"

    def save(self, *args, **kwargs):
        # Substituição de arquivo: apaga o antigo do disco.
        # Com 1GB por item, deixar o arquivo velho no HD é como enche o disco.
        old_file = None
        if self.pk:
            try:
                old_file = ArquivoItem.objects.get(pk=self.pk).arquivo
            except ArquivoItem.DoesNotExist:
                pass

        super().save(*args, **kwargs)

        if old_file and old_file.name and (not self.arquivo or old_file.name != self.arquivo.name):
            try:
                old_file.storage.delete(old_file.name)
            except Exception:
                pass


@receiver(post_delete, sender=ArquivoItem)
def delete_file_on_record_delete(sender, instance, **kwargs):
    """Apaga o arquivo físico quando o registro é removido de verdade."""
    if instance.arquivo and instance.arquivo.name:
        try:
            instance.arquivo.storage.delete(instance.arquivo.name)
        except Exception:
            pass