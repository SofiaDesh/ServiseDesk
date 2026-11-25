from django.urls import path
from . import views

app_name = 'support'

urlpatterns = [
    path('', views.ticket_list, name='ticket_list'),
    path('tickets/create/', views.ticket_create, name='ticket_create'),
    path('tickets/<int:pk>/', views.ticket_detail, name='ticket_detail'),

    path('kb/', views.kb_list, name='kb_list'),
    path('kb/create/', views.kb_create, name='kb_create'),
    path('kb/<int:pk>/', views.kb_detail, name='kb_detail'),
    path('kb/<int:pk>/edit/', views.kb_edit, name='kb_edit'),

    path('reports/', views.report_view, name='report'),
    path('reports/csv/', views.report_csv, name='report_csv'),

    path('profile/', views.profile_view, name='profile'),
    path('faq/', views.faq_view, name='faq'),

    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
]
