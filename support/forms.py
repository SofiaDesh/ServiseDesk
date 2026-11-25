import os
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from .models import User, Ticket, TicketMessage, KnowledgeArticle

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 МБ
ALLOWED_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.pdf', '.docx', '.zip', '.txt']
ALLOWED_MIME_TYPES = {
    'image/png',
    'image/jpeg',
    'application/pdf',
    'text/plain',
    'application/zip',
    'application/x-zip-compressed',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}
DANGEROUS_PARTS = {'.php', '.exe', '.bat', '.cmd', '.sh', '.js', '.html'}


class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form__input', 'placeholder': 'Введите логин'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form__input', 'placeholder': 'Введите пароль'}))


class RegisterForm(forms.ModelForm):
    password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(attrs={'class': 'form__input', 'placeholder': 'Минимум 8 символов'})
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form__input', 'placeholder': 'Повторите пароль'})
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email', 'department']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form__input', 'placeholder': 'Имя'}),
            'last_name': forms.TextInput(attrs={'class': 'form__input', 'placeholder': 'Фамилия'}),
            'username': forms.TextInput(attrs={'class': 'form__input', 'placeholder': 'Логин'}),
            'email': forms.EmailInput(attrs={'class': 'form__input', 'placeholder': 'mail@company.ru'}),
            'department': forms.TextInput(attrs={'class': 'form__input', 'placeholder': 'Отдел'}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password') != cleaned.get('password_confirm'):
            self.add_error('password_confirm', 'Пароли не совпадают. Введите одинаковый пароль в оба поля.')
        return cleaned


class TicketCreateForm(forms.ModelForm):
    attachment = forms.FileField(required=False, widget=forms.ClearableFileInput(attrs={'class': 'form__file'}))

    class Meta:
        model = Ticket
        fields = ['title', 'category', 'priority', 'description']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form__input', 'placeholder': 'Кратко опишите проблему'}),
            'category': forms.Select(attrs={'class': 'form__select'}),
            'priority': forms.Select(attrs={'class': 'form__select'}),
            'description': forms.Textarea(attrs={'class': 'form__textarea', 'rows': 4, 'placeholder': 'Подробности...'}),
        }

    def clean_title(self):
        title = self.cleaned_data.get('title', '').strip()
        if len(title) < 5:
            raise forms.ValidationError('Тема обращения слишком короткая. Укажите минимум 5 символов.')
        return title

    def clean_attachment(self):
        file_obj = self.cleaned_data.get('attachment')
        if not file_obj:
            return None
        if file_obj.size > MAX_FILE_SIZE:
            raise forms.ValidationError('Файл превышает допустимый размер 5 МБ. Сожмите файл и попробуйте снова.')
        name_lower = file_obj.name.lower()
        if any(part in name_lower for part in DANGEROUS_PARTS):
            raise forms.ValidationError('Недопустимое двойное или исполняемое расширение файла.')
        ext = os.path.splitext(name_lower)[1]
        content_type = getattr(file_obj, 'content_type', '')
        if ext not in ALLOWED_EXTENSIONS or (content_type and content_type not in ALLOWED_MIME_TYPES):
            raise forms.ValidationError('Недопустимый формат файла. Загрузите PNG, JPG, PDF, DOCX, ZIP или TXT.')
        return file_obj


class TicketManageForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['status', 'assignee']
        widgets = {
            'status': forms.Select(attrs={'class': 'form__select'}),
            'assignee': forms.Select(attrs={'class': 'form__select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assignee'].queryset = User.objects.filter(role__in=['specialist', 'manager'])
        self.fields['assignee'].empty_label = 'Не назначен'

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get('status')
        assignee = cleaned.get('assignee')
        if status and status.is_final and not assignee:
            self.add_error('assignee', 'Для перевода обращения в завершающий статус необходимо назначить исполнителя.')
        return cleaned


class MessageForm(forms.ModelForm):
    class Meta:
        model = TicketMessage
        fields = ['text']
        widgets = {
            'text': forms.TextInput(attrs={'class': 'form__input', 'placeholder': 'Напишите сообщение в чат...'}),
        }

    def clean_text(self):
        text = self.cleaned_data.get('text', '').strip()
        if len(text) < 3:
            raise forms.ValidationError('Сообщение слишком короткое. Введите минимум 3 символа.')
        return text


class ArticleForm(forms.ModelForm):
    tags_text = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form__input', 'placeholder': 'vpn, сеть, инструкция'})
    )

    class Meta:
        model = KnowledgeArticle
        fields = ['title', 'category', 'content']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form__input', 'placeholder': 'Заголовок статьи'}),
            'category': forms.Select(attrs={'class': 'form__select'}),
            'content': forms.Textarea(attrs={'class': 'form__textarea', 'rows': 6, 'placeholder': 'Текст инструкции...'}),
        }


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'department']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form__input'}),
            'last_name': forms.TextInput(attrs={'class': 'form__input'}),
            'email': forms.EmailInput(attrs={'class': 'form__input'}),
            'department': forms.TextInput(attrs={'class': 'form__input'}),
        }
