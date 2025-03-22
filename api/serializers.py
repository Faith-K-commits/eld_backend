from rest_framework import serializers
from .models import Trip, LogEntry, FuelStop

class FuelStopSerializer(serializers.ModelSerializer):
    class Meta:
        model = FuelStop
        fields = ['id', 'location', 'estimated_time']

class LogEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LogEntry
        fields = ['id', 'date', 'start_time', 'end_time', 'status', 'location', 'remarks']

class TripSerializer(serializers.ModelSerializer):
    log_entries = LogEntrySerializer(many=True, read_only=True)
    fuel_stops = FuelStopSerializer(many=True, read_only=True)

    class Meta:
        model = Trip
        fields = ['id', 'current_location', 'pickup_location', 'dropoff_location',
                 'current_cycle_used', 'created_at', 'log_entries', 'fuel_stops']