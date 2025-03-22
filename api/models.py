from django.db import models

class Trip(models.Model):
    current_location = models.CharField(max_length=255)
    pickup_location = models.CharField(max_length=255)
    dropoff_location = models.CharField(max_length=255)
    current_cycle_used = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Trip from {self.current_location} to {self.dropoff_location}"

class LogEntry(models.Model):
    trip = models.ForeignKey(Trip, related_name='log_entries', on_delete=models.CASCADE)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(max_length=50, choices=[
        ('OFF_DUTY', 'Off Duty'),
        ('SLEEPER_BERTH', 'Sleeper Berth'),
        ('DRIVING', 'Driving'),
        ('ON_DUTY', 'On Duty (Not Driving)'),
    ])
    location = models.CharField(max_length=255)
    remarks = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.date} - {self.status} - {self.start_time} to {self.end_time}"

class FuelStop(models.Model):
    trip = models.ForeignKey(Trip, related_name='fuel_stops', on_delete=models.CASCADE)
    location = models.CharField(max_length=255)
    estimated_time = models.DateTimeField()

    def __str__(self):
        return f"Fuel stop at {self.location}"