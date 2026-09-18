# /base_conhecimento/models.py
from django.db import models, transaction
from pgvector.django import VectorField
from django.db.models import Max
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from sistemas.models import Sistema
import re
import uuid
from ckeditor_uploader.fields import RichTextUploadingField

User = get_user_model()


class Artigo(models.Model):
    # ── Tipo do artigo ────────────────────────────────────────────
    # Antes a cor da tarja era decidida por `{% if 'ERRO' in titulo %}`
    # no template — ou seja, a classificação dependia de alguém lembrar
    # de escrever "ERRO" no título. Agora é um campo de verdade.
    TIPO_PROCEDIMENTO = "procedimento"
    TIPO_ERRO = "erro"
    TIPO_TUTORIAL = "tutorial"
    TIPO_FAQ = "faq"
    TIPOS = [
        (TIPO_PROCEDIMENTO, "Procedimento"),
        (TIPO_ERRO, "Erro / Troubleshooting"),
        (TIPO_TUTORIAL, "Tutorial"),
        (TIPO_FAQ, "FAQ"),
    ]

    # Identificação
    codigo = models.CharField(max_length=20, unique=True, editable=False, db_index=True)
    slug = models.SlugField(max_length=50, unique=True, editable=False)

    # Conteúdo principal
    titulo = models.CharField(max_length=255)
    conteudo = RichTextUploadingField()
    tipo = models.CharField(max_length=20, choices=TIPOS, default=TIPO_PROCEDIMENTO)
    sistema = models.ForeignKey(Sistema, on_delete=models.CASCADE, related_name="artigos")
    autor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="artigos"
    )


    hashtags = models.CharField(
        max_length=255,
        blank=True,
        help_text="Separe as hashtags por vírgula. Ex: instalação, erro, sql",
    )

    # ── Vetor semântico (RAG) ─────────────────────────────────────
    # Representação numérica do SIGNIFICADO do artigo, usada pela busca
    # da IA. Fica NULL até o artigo ser indexado (manage.py indexar_wiki).
    # Dimensão 768 = tamanho do embedding do modelo text-embedding-004
    # do Gemini. NÃO mexa nesse número depois de indexar.
    embedding = VectorField(dimensions=768, null=True, blank=True, editable=False)

    # Marca quando o vetor foi gerado, pra sabermos o que falta reindexar
    # quando um artigo é editado.
    embedding_atualizado_em = models.DateTimeField(null=True, blank=True, editable=False)

    # Controle
    visualizacoes = models.PositiveIntegerField(default=0, editable=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-atualizado_em"]
        indexes = [
            models.Index(fields=["sistema", "-atualizado_em"]),
        ]

    def __str__(self):
        return f"{self.titulo} ({self.codigo})"

    # ------------------------------------------------------------------
    # Geração de código
    # ------------------------------------------------------------------
    # PROBLEMA ANTIGO (dois bugs num só bloco de 4 linhas):
    #
    #   prefixo = self.sistema.nome[:2].upper()
    #   ultimo  = Artigo.objects.filter(sistema=self.sistema).count() + 1
    #   self.codigo = f"{prefixo}{ultimo:03d}"
    #
    #   1) COLISÃO ENTRE SISTEMAS: o prefixo vem das 2 primeiras letras do
    #      nome, mas `codigo` é unique GLOBAL. "Clipp Loja", "Clipp Food" e
    #      "Cloud Backup" geram todos "CL001" -> IntegrityError.
    #   2) COLISÃO POR DELEÇÃO: count()+1 reaproveita número. Com CL001 e
    #      CL003 no banco (CL002 apagado), o próximo vira CL003 -> já existe.
    #      Também sofre race condition com dois usuários salvando junto.
    #
    # SOLUÇÃO: prefixo derivado do ID do sistema (único por definição) e
    # sequência baseada no MAIOR código existente, dentro de transaction.
    # ------------------------------------------------------------------
    RE_SEQ = re.compile(r"(\d+)$")

    def _gerar_prefixo(self) -> str:
        """Prefixo estável e único por sistema."""
        base = slugify(self.sistema.nome or "").replace("-", "").upper()
        base = (base[:3] or "KB").ljust(3, "X")
        # o sufixo do ID desempata sistemas de nome parecido
        sufixo = str(self.sistema.pk)[-2:].upper().rjust(2, "0")
        return f"{base}{sufixo}"

    def _proximo_codigo(self) -> str:
        prefixo = self._gerar_prefixo()
        ultimo = (
            Artigo.objects.filter(codigo__startswith=prefixo)
            .aggregate(m=Max("codigo"))["m"]
        )
        seq = 1
        if ultimo:
            achado = self.RE_SEQ.search(ultimo)
            if achado:
                seq = int(achado.group(1)) + 1
        return f"{prefixo}-{seq:03d}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = uuid.uuid4().hex[:8]

        if not self.codigo:
            # a transação + retry evita que dois saves simultâneos peguem
            # o mesmo número
            for tentativa in range(5):
                try:
                    with transaction.atomic():
                        self.codigo = self._proximo_codigo()
                        return super().save(*args, **kwargs)
                except Exception:
                    if tentativa == 4:
                        # último recurso: sufixo aleatório, nunca colide
                        self.codigo = f"{self._gerar_prefixo()}-{uuid.uuid4().hex[:4].upper()}"
                        return super().save(*args, **kwargs)
                    self.codigo = ""
            return

        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    @property
    def tags_lista(self):
        """
        Hashtags como lista limpa.

        Antes cada view fazia `artigo.hashtags.split(",")` na mão — e quebrava
        se o campo viesse vazio/None.
        """
        if not self.hashtags:
            return []
        return [t.strip().lstrip("#") for t in self.hashtags.split(",") if t.strip()]

    # ------------------------------------------------------------------
    @property
    def dias_desde_atualizacao(self) -> int:
        from django.utils import timezone
        if not self.atualizado_em:
            return 0
        return (timezone.now() - self.atualizado_em).days

    @property
    def esta_desatualizado(self) -> bool:
        """
        Procedimento antigo parece igual a um de ontem — e o técnico segue
        o passo que não funciona mais. Documentação desatualizada é pior
        que ausente, então a tela avisa.

        Limiar: settings.BC_DIAS_DESATUALIZADO (padrão 365).
        """
        from django.conf import settings
        limite = getattr(settings, "BC_DIAS_DESATUALIZADO", 365)
        return self.dias_desde_atualizacao >= limite

    @property
    def idade_legivel(self) -> str:
        d = self.dias_desde_atualizacao
        if d >= 730:
            return f"há {d // 365} anos"
        if d >= 365:
            return "há mais de 1 ano"
        if d >= 60:
            return f"há {d // 30} meses"
        if d >= 30:
            return "há 1 mês"
        if d >= 1:
            return f"há {d} dias"
        return "hoje"


class ArtigoAcesso(models.Model):
    """
    Último acesso de cada usuário a cada artigo.

    Existe para o "Vistos recentemente": suporte é 80/20 — um punhado de
    artigos resolve a maioria das chamadas, e hoje eles são reencontrados
    do zero toda vez.

    Guarda UMA linha por (usuário, artigo) e só atualiza a data. Não vira
    tabela de log gigante.
    """
    usuario = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="artigos_acessados"
    )
    artigo = models.ForeignKey(
        Artigo, on_delete=models.CASCADE, related_name="acessos"
    )
    visto_em = models.DateTimeField(auto_now=True)
    vezes = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Acesso a artigo"
        verbose_name_plural = "Acessos a artigos"
        ordering = ["-visto_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "artigo"], name="unique_acesso_usuario_artigo"
            )
        ]
        indexes = [
            models.Index(fields=["usuario", "-visto_em"]),
        ]

    def __str__(self):
        return f"{self.usuario} -> {self.artigo.codigo}"