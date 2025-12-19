from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('administrator-acess/', admin.site.urls),
    path('', include('reservations.urls'))
    ]
