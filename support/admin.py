from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, Category, Priority, Status, Ticket,
    TicketMessage, Attachment, Tag, KnowledgeArticle, ArticleTag
)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'first_name', 'last_name', 'email', 'role', 'department')
    list_filter = ('role',)
    fieldsets = UserAdmin.fieldsets + (
        ('Роль в системе', {'fields': ('role', 'department')}),
    )


admin.site.register(Category)
admin.site.register(Priority)
admin.site.register(Status)
admin.site.register(Ticket)
admin.site.register(TicketMessage)
admin.site.register(Attachment)
admin.site.register(Tag)
admin.site.register(KnowledgeArticle)
admin.site.register(ArticleTag)
