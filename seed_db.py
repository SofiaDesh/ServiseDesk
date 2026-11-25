import os
from datetime import timedelta
import django
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from support.models import (
    ArticleTag, Category, KnowledgeArticle, Priority,
    Status, Tag, Ticket, TicketMessage, User
)


def run():
    # 1. Категории
    cat_net, _ = Category.objects.get_or_create(name='Сеть и VPN')
    cat_soft, _ = Category.objects.get_or_create(name='Программное обеспечение')
    cat_hard, _ = Category.objects.get_or_create(name='Оборудование')
    cat_acc, _ = Category.objects.get_or_create(name='Учетные записи')

    # 2. Приоритеты
    p_crit, _ = Priority.objects.get_or_create(level=4, defaults={'name': 'Критический', 'sla_hours': 4})
    p_high, _ = Priority.objects.get_or_create(level=3, defaults={'name': 'Высокий', 'sla_hours': 8})
    p_med, _ = Priority.objects.get_or_create(level=2, defaults={'name': 'Средний', 'sla_hours': 24})
    p_low, _ = Priority.objects.get_or_create(level=1, defaults={'name': 'Низкий', 'sla_hours': 72})

    # 3. Статусы
    s_new, _ = Status.objects.get_or_create(name='Новое', defaults={'is_final': False, 'sort_order': 1})
    s_work, _ = Status.objects.get_or_create(name='В работе', defaults={'is_final': False, 'sort_order': 2})
    s_done, _ = Status.objects.get_or_create(name='Решено', defaults={'is_final': True, 'sort_order': 3})

    # 4. Один базовый заявитель для проверки чужих заявок (логин: client, пароль: user12345)
    client_user, _ = User.objects.get_or_create(
        username='client',
        defaults={
            'email': 'client@company.local',
            'first_name': 'Иван',
            'last_name': 'Смирнов',
            'role': 'requester',
            'department': 'Бухгалтерия',
        }
    )
    client_user.set_password('user12345')
    client_user.save()

    now = timezone.now()

    # 5. По одному наглядному обращению на каждую категорию (всего 4 примера)
    examples = [
        (
            'Не подключается корпоративный VPN',
            'При запуске клиента появляется ошибка подключения к серверу.',
            cat_net, p_crit, s_work, now - timedelta(hours=6), now - timedelta(hours=2)  # просрочена
        ),
        (
            'Установка 1С на новый компьютер',
            'Прошу установить платформу 1С:Предприятие и настроить доступ к базе.',
            cat_soft, p_high, s_new, now - timedelta(hours=1), now + timedelta(hours=7)
        ),
        (
            'Не печатает сетевой принтер в кабинете 204',
            'Документы зависают в очереди печати.',
            cat_hard, p_med, s_work, now - timedelta(hours=3), now + timedelta(hours=21)
        ),
        (
            'Сброс пароля от корпоративной почты',
            'Забыл пароль от почтового ящика после отпуска.',
            cat_acc, p_low, s_done, now - timedelta(hours=10), now + timedelta(hours=62)
        ),
    ]

    for title, desc, cat, prio, st, created, deadline in examples:
        ticket, is_created = Ticket.objects.get_or_create(
            title=title,
            defaults={
                'description': desc,
                'author': client_user,
                'category': cat,
                'priority': prio,
                'status': st,
                'created_at': created,
                'deadline': deadline,
                'resolved_at': now if st.is_final else None,
            }
        )
        if is_created:
            TicketMessage.objects.create(
                ticket=ticket,
                sender=client_user,
                text='Здравствуйте! Подскажите, пожалуйста, когда получится посмотреть?',
            )

    # 6. Две статьи в Базе знаний
    art1, _ = KnowledgeArticle.objects.get_or_create(
        title='Настройка VPN на рабочем компьютере',
        defaults={
            'content': '1. Откройте VPN-клиент.\n2. Импортируйте профиль из письма.\n3. Нажмите Подключить.',
            'category': cat_net,
            'author': client_user,
        }
    )
    tag_vpn, _ = Tag.objects.get_or_create(name='vpn')
    ArticleTag.objects.get_or_create(article=art1, tag=tag_vpn, defaults={'added_by': client_user})

    art2, _ = KnowledgeArticle.objects.get_or_create(
        title='Как подключить сетевой принтер',
        defaults={
            'content': '1. Откройте Параметры -> Принтеры.\n2. Нажмите Добавить принтер по IP-адресу.',
            'category': cat_hard,
            'author': client_user,
        }
    )
    tag_pr, _ = Tag.objects.get_or_create(name='принтер')
    ArticleTag.objects.get_or_create(article=art2, tag=tag_pr, defaults={'added_by': client_user})

    print('Готово! Справочники, 4 примера заявок и 2 статьи Базы знаний загружены.')
    print('Теперь создайте свой аккаунт руководителя командой: python manage.py createsuperuser')


if __name__ == '__main__':
    run()
