from django.urls import path
from . import views

urlpatterns = [
    path('trips/', views.trip_list, name='trip-list'),
    path('trips/create/', views.trip_create, name='trip-create'),
    path('trips/<int:pk>/', views.trip_detail, name='trip-detail'),
    path('trips/<int:pk>/generate-logs/', views.generate_trip_logs, name='generate-trip-logs'),
]