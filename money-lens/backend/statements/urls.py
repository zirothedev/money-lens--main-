from django.urls import path

from . import views

app_name = 'statements'

urlpatterns = [
    path('upload/', views.upload_statement, name='upload'),
    path('<uuid:job_id>/', views.job_status, name='status'),
    path('<uuid:job_id>/process/', views.process_statement, name='process'),
]
