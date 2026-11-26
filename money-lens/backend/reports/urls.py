from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.report_list, name='list'),
    path('history/', views.report_history, name='history'),
    path('<uuid:report_id>/', views.report_detail, name='detail'),
    path('<uuid:report_id>/data/', views.report_data, name='data'),
]
