import os
import django
import sys

# Adiciona o caminho do projeto no PYTHONPATH
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "union.settings")
django.setup()

# Agora importa os models
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType


from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.utils.text import slugify  # 🔹 Para gerar codenames seguros
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = "Cria grupos, usuários e permissões iniciais"

    def handle(self, *args, **options):
        # === Módulos ===
        modulos = [
            "Whatsapp Bot",
            "Atendimento e chamados internos",
            "Clientes e sistemas",
            "Base de conhecimento",
            "Cofre de senhas",
            "Arquivos e instaladores",
            "Calendario e agenda",
            "Controle de horas",
            "Gestão de implantação",
            "CS - Satisfação do Cliente",
        ]

        # Criar permissões custom (ligadas a um ContentType genérico)
        ct, _ = ContentType.objects.get_or_create(
            app_label="core", model="modulo"
        )

        perms = {}
        for m in modulos:
            codename = slugify(m).replace("-", "_")  # 🔹 evita acentos e espaços
            p, _ = Permission.objects.get_or_create(
                codename=codename,
                name=f"Acesso ao módulo {m}",
                content_type=ct,
            )
            perms[m] = p

        # === Grupos e suas permissões ===
        grupos = {
            "Suporte": [
                "Whatsapp Bot",
                "Atendimento e chamados internos",
                "Clientes e sistemas",
                "Base de conhecimento",
                "Cofre de senhas",
                "Arquivos e instaladores",
                "Calendario e agenda",
                "Controle de horas",
            ],
            "Assistencia": [
                "Whatsapp Bot",
                "Atendimento e chamados internos",
                "Clientes e sistemas",
                "Calendario e agenda",
            ],
            "Implantação": [
                "Gestão de implantação",
                "CS - Satisfação do Cliente",
            ],
            "Comercial": [
                "Whatsapp Bot",
                "Atendimento e chamados internos",
                "Clientes e sistemas",
            ],
            "Financeiro": [
                "Whatsapp Bot",
                "Atendimento e chamados internos",
                "Clientes e sistemas",
            ],
            "Compras": [
                "Whatsapp Bot",
                "Atendimento e chamados internos",
                "Clientes e sistemas",
            ],
            "CS": [
                "Gestão de implantação",
                "CS - Satisfação do Cliente",
            ],
        }

        grupo_objs = {}
        for g, mods in grupos.items():
            grp, _ = Group.objects.get_or_create(name=g)
            grp.permissions.set([perms[m] for m in mods])
            grupo_objs[g] = grp

        # === Usuários ===
        usuarios = {
            "Gilberto": ["Suporte", "Implantação"],
            "Daniel": ["Suporte", "Implantação"],
            "Carlos": ["Suporte"],
            "Leticia": ["Suporte"],
            "Silas": ["Suporte", "Implantação"],
            "Jerry": ["Comercial"],
            "Henrique": ["Comercial"],  # ✅ Corrigido
            "Samara": ["Financeiro"],
            "Assistencia": ["Assistencia"],
            "Financeiro": ["Financeiro"],
            "Compras": ["Compras"],
        }

        for nome, grupos_user in usuarios.items():
            u, created = User.objects.get_or_create(
                username=nome.lower(),
                defaults={"email": f"{nome.lower()}@exemplo.com"}
            )
            if created:
                u.set_password("123456")  # 🔑 senha inicial (alterar em produção)
                u.is_active = True
                u.save()
            u.groups.set([grupo_objs[g] for g in grupos_user])

        self.stdout.write(self.style.SUCCESS(
            "✅ Usuários, grupos e permissões criados com sucesso!"
        ))
