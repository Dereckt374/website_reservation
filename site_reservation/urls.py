from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('administrator-acess/', admin.site.urls, name="admin-access"),
    path('', include('reservations.urls'))
    ]
