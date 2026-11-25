from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import Client, TestCase
from django.urls import reverse

from .forms import TicketCreateForm
from .models import Attachment, Category, Priority, Status, Ticket, User
from .views import create_ticket_atomic, get_report_stats


class ExceptionHandlingNegativeTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.cat = Category.objects.create(name='Сеть и VPN')
        self.prio = Priority.objects.create(name='Критический', level=4, sla_hours=4)
        self.status_new = Status.objects.create(name='Новое', is_final=False, sort_order=1)

        self.user1 = User.objects.create_user(
            username='user1', email='u1@company.local', password='StrongPassword123!', role='requester'
        )
        self.user2 = User.objects.create_user(
            username='user2', email='u2@company.local', password='StrongPassword123!', role='requester'
        )
        self.ticket_u1 = Ticket.objects.create(
            title='Заявка первого пользователя',
            description='Описание проблемы первого пользователя',
            author=self.user1,
            category=self.cat,
            priority=self.prio,
            status=self.status_new,
        )

    def test_1_nonexistent_ticket_returns_404(self):
        """1. Обращение к несуществующей записи возвращает статус 404."""
        self.client.login(username='user1', password='StrongPassword123!')
        response = self.client.get(reverse('support:ticket_detail', kwargs={'pk': 99999}))
        self.assertEqual(response.status_code, 404)

    def test_2_foreign_ticket_access_returns_403(self):
        """2. Попытка заявителя открыть чужое обращение возвращает статус 403."""
        self.client.login(username='user2', password='StrongPassword123!')
        response = self.client.get(reverse('support:ticket_detail', kwargs={'pk': self.ticket_u1.pk}))
        self.assertEqual(response.status_code, 403)

    def test_3_invalid_form_does_not_create_record_and_shows_message(self):
        """3. Форма с неверными данными (файл > 5 МБ и короткая тема) не создает запись и выводит ошибку."""
        self.client.login(username='user1', password='StrongPassword123!')
        initial_count = Ticket.objects.count()
        big_file = SimpleUploadedFile('big.zip', b'x' * (5 * 1024 * 1024 + 100), content_type='application/zip')

        response = self.client.post(reverse('support:ticket_create'), {
            'title': 'Абв',
            'category': self.cat.id,
            'priority': self.prio.id,
            'description': 'Тестовое описание',
            'attachment': big_file,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Ticket.objects.count(), initial_count)
        self.assertContains(response, 'Тема обращения слишком короткая')
        self.assertContains(response, 'Файл превышает допустимый размер 5 МБ')

    def test_4_transaction_rollback_on_mid_operation_error(self):
        """4. При ошибке в середине операции (сбой сохранения вложения) заявка откатывается полностью."""
        initial_tickets = Ticket.objects.count()
        test_file = SimpleUploadedFile('ok.txt', b'hello world', content_type='text/plain')
        form = TicketCreateForm(
            data={
                'title': 'Тестовая заявка для проверки отката',
                'category': self.cat.id,
                'priority': self.prio.id,
                'description': 'Описание заявки',
            },
            files={'attachment': test_file},
        )
        self.assertTrue(form.is_valid())

        with patch.object(Attachment.objects, 'create', side_effect=DatabaseError('Сбой записи вложения')):
            with self.assertRaises(DatabaseError):
                create_ticket_atomic(self.user1, form)

        self.assertEqual(Ticket.objects.count(), initial_tickets)

    def test_5_report_calculation_on_empty_queryset_does_not_crash(self):
        """5. Расчет показателей отчета на пустой выборке не вызывает деление на ноль."""
        Ticket.objects.all().delete()
        stats = get_report_stats()
        self.assertEqual(stats['total'], 0)
        self.assertEqual(stats['overdue'], 0)
        self.assertEqual(stats['overdue_percent'], 0.0)
