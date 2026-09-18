from django.contrib import admin
from .models import RaioXConfig

@admin.register(RaioXConfig)
class RaioXConfigAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'senha_mestra', 'peso_os', 'peso_implantacao', 'peso_cs', 'peso_agenda', 'peso_msg_zap')
    
    def has_add_permission(self, request):
        # Bloqueia a criação de uma segunda configuração (para manter apenas uma)
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        # Impede de deletar a configuração sem querer
        return False