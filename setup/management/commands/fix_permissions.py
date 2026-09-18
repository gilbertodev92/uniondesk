from django.core.management.base import BaseCommand
from django.contrib.auth.models import Permission, Group, ContentType
from django.apps import apps

class Command(BaseCommand):
    help = "Cria permissões de módulos e atribui aos grupos certos"

    def handle(self, *args, **options):
        # Escolha um app para vincular as permissões
        app_label = 'users'  # pode ser 'core' ou qualquer app seu existente
        content_type, created = ContentType.objects.get_or_create(
            app_label=app_label,
            model='modulo_permission'  # nome genérico
        )

        # Lista de módulos e grupos que terão acesso
        modulos = [
            {"nome": "Whatsapp Bot", "codename": "whatsapp_bot", "grupos": ["Grupo1", "Grupo2"]},
            {"nome": "Atendimentos e chamados internos", "codename": "atendimentos_chamados", "grupos": ["Grupo1"]},
            {"nome": "Clientes e sistemas", "codename": "clientes_sistemas", "grupos": ["Grupo1"]},
            {"nome": "Gestão de implantações", "codename": "implantacao", "grupos": ["Grupo2"]},
            {"nome": "CS - Satisfação do Cliente", "codename": "cs_satisfacao", "grupos": ["Grupo2"]},
            {"nome": "Base de conhecimento", "codename": "base_conhecimento", "grupos": ["Grupo1", "Grupo2"]},
            {"nome": "Cofre de senhas", "codename": "cofre_senhas", "grupos": ["Grupo1", "Grupo2"]},
            {"nome": "Arquivos e instaladores", "codename": "arquivos_instaladores", "grupos": ["Grupo1"]},
            {"nome": "Calendário e agenda", "codename": "calendario_agenda", "grupos": ["Grupo1", "Grupo2"]},
            {"nome": "Controle de horas", "codename": "controle_horas", "grupos": ["Grupo1", "Grupo2"]},
        ]

        for m in modulos:
            perm, created = Permission.objects.get_or_create(
                codename=m["codename"],
                name=f"Acesso ao módulo {m['nome']}",
                content_type=content_type
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Permissão criada: {m['nome']}"))

            # Atribui permissão aos grupos
            for g_nome in m["grupos"]:
                grupo, created_group = Group.objects.get_or_create(name=g_nome)
                grupo.permissions.add(perm)
                if created_group:
                    self.stdout.write(self.style.SUCCESS(f"Grupo criado: {g_nome}"))
                self.stdout.write(self.style.SUCCESS(f"Permissão '{m['nome']}' adicionada ao grupo '{g_nome}'"))

        self.stdout.write(self.style.SUCCESS("Permissões e grupos atualizados com sucesso!"))
