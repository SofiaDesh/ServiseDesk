import csv
import logging
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .exceptions import TicketWorkflowError
from .forms import (
    ArticleForm, LoginForm, MessageForm, ProfileForm,
    RegisterForm, TicketCreateForm, TicketManageForm
)
from .models import (
    ArticleTag, Attachment, Category, KnowledgeArticle,
    Priority, Status, Tag, Ticket, User
)

logger = logging.getLogger('support')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('support:ticket_list')

    attempts = request.session.get('login_attempts', 0)
    if attempts >= 5:
        logger.warning('Превышено число попыток входа (5) для текущей сессии.')
        messages.error(request, 'Слишком много неудачных попыток входа. Повторите попытку позже.')
        return render(request, 'registration/login.html', {'form': LoginForm(request)})

    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            request.session['login_attempts'] = 0
            login(request, form.get_user())
            return redirect('support:ticket_list')
        request.session['login_attempts'] = attempts + 1
        logger.warning('Неудачная попытка входа в систему.')

    return render(request, 'registration/login.html', {'form': form})


def register_view(request):
    if request.user.is_authenticated:
        return redirect('support:ticket_list')

    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save(commit=False)
                user.role = 'requester'
                user.set_password(form.cleaned_data['password'])
                user.save()
        except IntegrityError as exc:
            logger.error('Ошибка уникальности при регистрации пользователя: %s', exc)
            messages.error(request, 'Пользователь с таким логином или email уже существует.')
            return render(request, 'registration/register.html', {'form': form})

        login(request, user)
        messages.success(request, 'Вы успешно зарегистрировались!')
        return redirect('support:ticket_list')

    return render(request, 'registration/register.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('support:login')


@login_required
def ticket_list(request):
    if request.user.role == 'requester':
        tickets = Ticket.objects.filter(author=request.user)
    else:
        tickets = Ticket.objects.all()

    tickets = tickets.select_related('category', 'priority', 'status', 'author', 'assignee')

    q = request.GET.get('q', '').strip()
    if q:
        tickets = tickets.filter(
            Q(ticket_number__icontains=q) |
            Q(title__icontains=q) |
            Q(description__icontains=q)
        )

    status_id = request.GET.get('status', '')
    category_id = request.GET.get('category', '')
    priority_id = request.GET.get('priority', '')
    if status_id.isdigit():
        tickets = tickets.filter(status_id=int(status_id))
    if category_id.isdigit():
        tickets = tickets.filter(category_id=int(category_id))
    if priority_id.isdigit():
        tickets = tickets.filter(priority_id=int(priority_id))

    sort = request.GET.get('sort', '-created_at')
    if sort in ('-created_at', 'deadline', '-priority__level'):
        tickets = tickets.order_by(sort)

    all_list = list(tickets)
    overdue_count = sum(1 for t in all_list if t.is_overdue)

    page_obj = Paginator(all_list, 20).get_page(request.GET.get('page'))

    return render(request, 'support/ticket_list.html', {
        'page_obj': page_obj,
        'total_count': len(all_list),
        'overdue_count': overdue_count,
        'categories': Category.objects.all(),
        'priorities': Priority.objects.all(),
        'statuses': Status.objects.all(),
        'q': q,
        'selected_status': status_id,
        'selected_category': category_id,
        'selected_priority': priority_id,
        'selected_sort': sort,
    })


def create_ticket_atomic(user, form):
    with transaction.atomic():
        default_status = Status.objects.order_by('sort_order').first()
        if not default_status:
            raise TicketWorkflowError('В справочнике не настроены статусы обращений.')
        ticket = form.save(commit=False)
        ticket.author = user
        ticket.status = default_status
        ticket.save()

        uploaded_file = form.cleaned_data.get('attachment')
        if uploaded_file:
            Attachment.objects.create(
                ticket=ticket,
                uploaded_by=user,
                file=uploaded_file,
                original_name=uploaded_file.name,
            )
    return ticket


@login_required
def ticket_create(request):
    form = TicketCreateForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        try:
            ticket = create_ticket_atomic(request.user, form)
        except (TicketWorkflowError, DatabaseError) as exc:
            logger.error('Ошибка при создании обращения: %s', exc)
            messages.error(request, f'Не удалось создать обращение: {exc}')
            return render(request, 'support/ticket_create.html', {'form': form})

        messages.success(request, f'Обращение {ticket.ticket_number} создано!')
        return redirect('support:ticket_detail', pk=ticket.pk)

    return render(request, 'support/ticket_create.html', {'form': form})


@login_required
def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)

    if request.user.role == 'requester' and ticket.author != request.user:
        logger.warning('Попытка несанкционированного доступа (403) к обращению id=%s', pk)
        return render(request, '403.html', status=403)

    message_form = MessageForm()
    manage_form = TicketManageForm(instance=ticket)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'send_message':
            if ticket.status.is_final:
                messages.error(request, 'Обращение уже закрыто. Отправка новых сообщений невозможна.')
                return redirect('support:ticket_detail', pk=ticket.pk)
            message_form = MessageForm(request.POST)
            if message_form.is_valid():
                msg = message_form.save(commit=False)
                msg.ticket = ticket
                msg.sender = request.user
                msg.save()
                return redirect('support:ticket_detail', pk=ticket.pk)

        elif action == 'manage_ticket' and request.user.role != 'requester':
            old_status = ticket.status.name
            manage_form = TicketManageForm(request.POST, instance=ticket)
            if manage_form.is_valid():
                updated = manage_form.save()
                if updated.status.name != old_status:
                    try:
                        send_mail(
                            subject=f'Изменен статус обращения {updated.ticket_number}',
                            message=f'Новый статус вашего обращения: {updated.status.name}',
                            from_email=None,
                            recipient_list=[updated.author.email],
                            fail_silently=False,
                        )
                    except Exception as mail_exc:
                        logger.error('Ошибка отправки email по обращению %s: %s', updated.ticket_number, mail_exc)
                messages.success(request, 'Изменения сохранены.')
                return redirect('support:ticket_detail', pk=ticket.pk)

    return render(request, 'support/ticket_detail.html', {
        'ticket': ticket,
        'chat_messages': ticket.messages.select_related('sender').all(),
        'attachments': ticket.attachments.all(),
        'message_form': message_form,
        'manage_form': manage_form,
    })


@login_required
def kb_list(request):
    articles = KnowledgeArticle.objects.select_related('category', 'author').prefetch_related('tags').all()
    q = request.GET.get('q', '').strip()
    tag_name = request.GET.get('tag', '').strip()

    if q:
        articles = articles.filter(Q(title__icontains=q) | Q(content__icontains=q))
    if tag_name:
        articles = articles.filter(tags__name=tag_name)

    return render(request, 'support/kb_list.html', {
        'articles': articles,
        'tags': Tag.objects.all(),
        'q': q,
        'selected_tag': tag_name,
    })


@login_required
def kb_detail(request, pk):
    article = get_object_or_404(KnowledgeArticle, pk=pk)
    return render(request, 'support/kb_detail.html', {'article': article})


def save_tags(article, tags_text, user):
    ArticleTag.objects.filter(article=article).delete()
    if not tags_text:
        return
    for raw in tags_text.split(','):
        name = raw.strip().lstrip('#').lower()
        if name:
            tag_obj, _ = Tag.objects.get_or_create(name=name)
            ArticleTag.objects.get_or_create(article=article, tag=tag_obj, defaults={'added_by': user})


@login_required
def kb_create(request):
    if request.user.role == 'requester':
        logger.warning('Попытка создания статьи БЗ без прав (403).')
        return render(request, '403.html', status=403)

    form = ArticleForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            article = form.save(commit=False)
            article.author = request.user
            article.save()
            save_tags(article, form.cleaned_data.get('tags_text'), request.user)
        messages.success(request, 'Статья добавлена в Базу знаний!')
        return redirect('support:kb_detail', pk=article.pk)

    return render(request, 'support/kb_form.html', {'form': form, 'is_edit': False})


@login_required
def kb_edit(request, pk):
    if request.user.role == 'requester':
        return render(request, '403.html', status=403)

    article = get_object_or_404(KnowledgeArticle, pk=pk)
    initial_tags = ', '.join(t.name for t in article.tags.all())
    form = ArticleForm(request.POST or None, instance=article, initial={'tags_text': initial_tags})

    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            article = form.save()
            save_tags(article, form.cleaned_data.get('tags_text'), request.user)
        messages.success(request, 'Статья обновлена!')
        return redirect('support:kb_detail', pk=article.pk)

    return render(request, 'support/kb_form.html', {'form': form, 'is_edit': True})


def get_report_stats():
    tickets = list(Ticket.objects.select_related('category', 'status').all())
    total = len(tickets)
    overdue = sum(1 for t in tickets if t.is_overdue)
    in_time = total - overdue
    # Безопасное деление: защита от ZeroDivisionError при пустой базе
    percent = round((overdue / total) * 100, 1) if total > 0 else 0.0

    rows = []
    for cat in Category.objects.all():
        cat_list = [t for t in tickets if t.category_id == cat.id]
        c_total = len(cat_list)
        c_overdue = sum(1 for t in cat_list if t.is_overdue)
        c_in_time = c_total - c_overdue
        c_percent = round((c_overdue / c_total) * 100, 1) if c_total > 0 else 0.0
        rows.append({
            'name': cat.name,
            'total': c_total,
            'in_time': c_in_time,
            'overdue': c_overdue,
            'percent': c_percent,
        })

    return {
        'total': total,
        'in_time': in_time,
        'overdue': overdue,
        'overdue_percent': percent,
        'by_category': rows,
    }


@login_required
def report_view(request):
    if request.user.role != 'manager':
        logger.warning('Попытка доступа к отчету руководителя без прав (403).')
        return render(request, '403.html', status=403)
    return render(request, 'support/report.html', get_report_stats())


@login_required
def report_csv(request):
    if request.user.role != 'manager':
        return render(request, '403.html', status=403)

    stats = get_report_stats()
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="sla_report.csv"'

    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Категория', 'Всего', 'В срок', 'Просрочено', 'Доля просрочки (%)'])
    for r in stats['by_category']:
        writer.writerow([r['name'], r['total'], r['in_time'], r['overdue'], r['percent']])
    writer.writerow(['ИТОГО', stats['total'], stats['in_time'], stats['overdue'], stats['overdue_percent']])
    return response


@login_required
def profile_view(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        try:
            form.save()
            messages.success(request, 'Профиль обновлен.')
            return redirect('support:profile')
        except IntegrityError as exc:
            logger.error('Ошибка уникальности email при обновлении профиля: %s', exc)
            messages.error(request, 'Этот адрес электронной почты уже занят другим пользователем.')

    return render(request, 'support/profile.html', {
        'form': form,
        'my_tickets_count': Ticket.objects.filter(author=request.user).count(),
    })


@login_required
def faq_view(request):
    return render(request, 'support/faq.html', {'priorities': Priority.objects.all()})
