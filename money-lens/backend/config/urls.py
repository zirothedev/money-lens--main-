from django.contrib import admin
from django.urls import include, path
from .health import health_check
from .views import home

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health_check, name='health'),
    path('accounts/', include('accounts.urls')),
    path('statements/', include('statements.urls')),
    path('reports/', include('reports.urls')),
    path('', home, name='home'),
]
