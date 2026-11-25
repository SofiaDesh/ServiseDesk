from datetime import timedelta
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    ROLE_CHOICES = [
        ('requester', 'Заявитель'),
        ('specialist', 'Специалист'),
        ('manager', 'Руководитель'),
    ]

    email = models.EmailField('Электронная почта', unique=True)
    role = models.CharField('Роль', max_length=20, choices=ROLE_CHOICES, default='requester')
    department = models.CharField('Отдел', max_length=100, blank=True)

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = 'manager'
        super().save(*args, **kwargs)

    def __str__(self):
        name = self.get_full_name().strip()
        return f'{name} ({self.get_role_display()})' if name else self.username


class Category(models.Model):
    name = models.CharField('Название категории', max_length=100, unique=True)

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'
        ordering = ['name']

    def __str__(self):
        return self.name


class Priority(models.Model):
    name = models.CharField('Название приоритета', max_length=50, unique=True)
    level = models.PositiveSmallIntegerField('Уровень важности', unique=True)
    sla_hours = models.PositiveIntegerField('Срок решения (часов)')

    class Meta:
        verbose_name = 'Приоритет'
        verbose_name_plural = 'Приоритеты'
        ordering = ['-level']

    def __str__(self):
        return f'{self.name} ({self.sla_hours} ч.)'


class Status(models.Model):
    name = models.CharField('Название статуса', max_length=50, unique=True)
    is_final = models.BooleanField('Завершающий статус', default=False)
    sort_order = models.PositiveSmallIntegerField('Порядок', default=1)

    class Meta:
        verbose_name = 'Статус'
        verbose_name_plural = 'Статусы'
        ordering = ['sort_order']

    def __str__(self):
        return self.name


class Ticket(models.Model):
    ticket_number = models.CharField('Номер обращения', max_length=20, unique=True, editable=False)
    title = models.CharField('Тема обращения', max_length=200)
    description = models.TextField('Описание проблемы')
    author = models.ForeignKey(User, verbose_name='Заявитель', on_delete=models.CASCADE, related_name='authored_tickets')
    assignee = models.ForeignKey(
        User, verbose_name='Исполнитель', on_delete=models.SET_NULL,
        related_name='assigned_tickets', null=True, blank=True
    )
    category = models.ForeignKey(Category, verbose_name='Категория', on_delete=models.PROTECT)
    priority = models.ForeignKey(Priority, verbose_name='Приоритет', on_delete=models.PROTECT)
    status = models.ForeignKey(Status, verbose_name='Статус', on_delete=models.PROTECT)
    created_at = models.DateTimeField('Дата создания', default=timezone.now)
    deadline = models.DateTimeField('Крайний срок (SLA)')
    resolved_at = models.DateTimeField('Дата решения', null=True, blank=True)

    class Meta:
        verbose_name = 'Обращение'
        verbose_name_plural = 'Обращения'
        ordering = ['-created_at']

    @property
    def is_overdue(self):
        if self.status.is_final:
            return bool(self.resolved_at and self.resolved_at > self.deadline)
        return timezone.now() > self.deadline

    def save(self, *args, **kwargs):
        if not self.created_at:
            self.created_at = timezone.now()
        if not self.deadline and self.priority_id:
            self.deadline = self.created_at + timedelta(hours=self.priority.sla_hours)
        if self.status_id and self.status.is_final and not self.resolved_at:
            self.resolved_at = timezone.now()
        elif self.status_id and not self.status.is_final:
            self.resolved_at = None

        is_new = self.pk is None
        if is_new and not self.ticket_number:
            super().save(*args, **kwargs)
            self.ticket_number = f'SD-{self.created_at.year}-{self.pk:04d}'
            super().save(update_fields=['ticket_number'])
            return
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.ticket_number}: {self.title}'


class TicketMessage(models.Model):
    ticket = models.ForeignKey(Ticket, verbose_name='Обращение', on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, verbose_name='Отправитель', on_delete=models.CASCADE)
    text = models.TextField('Текст сообщения')
    created_at = models.DateTimeField('Дата отправки', default=timezone.now)

    class Meta:
        verbose_name = 'Сообщение'
        verbose_name_plural = 'Сообщения'
        ordering = ['created_at']

    def __str__(self):
        return f'Сообщение к {self.ticket.ticket_number}'


class Attachment(models.Model):
    ticket = models.ForeignKey(Ticket, verbose_name='Обращение', on_delete=models.CASCADE, related_name='attachments')
    uploaded_by = models.ForeignKey(User, verbose_name='Загрузил', on_delete=models.CASCADE)
    file = models.FileField('Файл', upload_to='attachments/%Y/%m/')
    original_name = models.CharField('Имя файла', max_length=255)
    uploaded_at = models.DateTimeField('Дата загрузки', default=timezone.now)

    class Meta:
        verbose_name = 'Вложение'
        verbose_name_plural = 'Вложения'

    def __str__(self):
        return self.original_name


class Tag(models.Model):
    name = models.CharField('Тег', max_length=50, unique=True)

    class Meta:
        verbose_name = 'Тег'
        verbose_name_plural = 'Теги'
        ordering = ['name']

    def __str__(self):
        return f'#{self.name}'


class KnowledgeArticle(models.Model):
    title = models.CharField('Заголовок', max_length=200)
    content = models.TextField('Текст статьи')
    category = models.ForeignKey(Category, verbose_name='Категория', on_delete=models.PROTECT)
    author = models.ForeignKey(User, verbose_name='Автор', on_delete=models.CASCADE)
    tags = models.ManyToManyField(Tag, verbose_name='Теги', through='ArticleTag', blank=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)

    class Meta:
        verbose_name = 'Статья базы знаний'
        verbose_name_plural = 'Статьи базы знаний'
        ordering = ['-updated_at']

    def __str__(self):
        return self.title


class ArticleTag(models.Model):
    article = models.ForeignKey(KnowledgeArticle, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)
    added_by = models.ForeignKey(User, on_delete=models.CASCADE)
    added_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Тег статьи'
        verbose_name_plural = 'Теги статей'
        unique_together = ('article', 'tag')
