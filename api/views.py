import json
import datetime
import requests
import math
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Trip, LogEntry, FuelStop
from .serializers import TripSerializer, LogEntrySerializer, FuelStopSerializer
from django.conf import settings

# Use OpenStreetMap's free Nominatim for geocoding and OSRM for routing
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/"

@api_view(['POST'])
def trip_create(request):
    serializer = TripSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
def trip_detail(request, pk):
    try:
        trip = Trip.objects.get(pk=pk)
    except Trip.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = TripSerializer(trip)
        return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'PUT':
        serializer = TripSerializer(trip, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        trip.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['POST'])
def generate_trip_logs(request, pk):
    try:
        trip = Trip.objects.get(pk=pk)
    except Trip.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    # Calculate route and generate logs
    route_data = calculate_route(
        trip.current_location,
        trip.pickup_location,
        trip.dropoff_location
    )

    if not route_data:
        return Response(
            {"error": "Failed to calculate route"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Generate logs based on route
    logs = generate_eld_logs(trip, route_data, trip.current_cycle_used)

    return Response({
        "route": route_data,
        "logs": LogEntrySerializer(logs, many=True).data
    })

def geocode(location):
    """Convert location name to coordinates"""
    params = {
        "q": location,
        "format": "json",
        "limit": 1
    }

    response = requests.get(NOMINATIM_URL, params=params, headers={
        "User-Agent": "ELD-App/1.0"
    })

    if response.status_code == 200 and response.json():
        data = response.json()[0]
        return {
            "lat": float(data["lat"]),
            "lon": float(data["lon"]),
            "display_name": data["display_name"]
        }
    return None

def calculate_route(from_location, pickup_location, to_location):
    """Calculate route using OSRM service"""
    # Geocode locations
    from_coords = geocode(from_location)
    pickup_coords = geocode(pickup_location)
    to_coords = geocode(to_location)

    if not all([from_coords, pickup_coords, to_coords]):
        return None

    # Get route from current to pickup
    first_leg_url = f"{OSRM_URL}{from_coords['lon']},{from_coords['lat']};{pickup_coords['lon']},{pickup_coords['lat']}?overview=full&geometries=geojson"
    first_leg_response = requests.get(first_leg_url)

    # Get route from pickup to dropoff
    second_leg_url = f"{OSRM_URL}{pickup_coords['lon']},{pickup_coords['lat']};{to_coords['lon']},{to_coords['lat']}?overview=full&geometries=geojson"
    second_leg_response = requests.get(second_leg_url)

    if first_leg_response.status_code != 200 or second_leg_response.status_code != 200:
        return None

    first_leg_data = first_leg_response.json()
    second_leg_data = second_leg_response.json()

    if first_leg_data["code"] != "Ok" or second_leg_data["code"] != "Ok":
        return None

    # Calculate total distance (in meters) and duration (in seconds)
    total_distance_meters = first_leg_data["routes"][0]["distance"] + second_leg_data["routes"][0]["distance"]
    total_duration_seconds = first_leg_data["routes"][0]["duration"] + second_leg_data["routes"][0]["duration"]

    # Convert to miles and hours
    total_distance_miles = total_distance_meters * 0.000621371
    total_duration_hours = total_duration_seconds / 3600

    # Combine route geometries
    combined_geometry = {
        "type": "LineString",
        "coordinates": (
            first_leg_data["routes"][0]["geometry"]["coordinates"] +
            second_leg_data["routes"][0]["geometry"]["coordinates"]
        )
    }

    # Calculate fuel stops (every 1000 miles)
    fuel_stops = []
    fuel_distance = 1000  # miles
    num_fuel_stops = math.floor(total_distance_miles / fuel_distance)

    for i in range(num_fuel_stops):
        stop_distance = (i + 1) * fuel_distance
        stop_percentage = stop_distance / total_distance_miles

        # Simplistic approach - get a point along the route
        stop_index = min(
            int(len(combined_geometry["coordinates"]) * stop_percentage),
            len(combined_geometry["coordinates"]) - 1
        )

        stop_coords = combined_geometry["coordinates"][stop_index]
        fuel_stops.append({
            "coordinates": stop_coords,
            "distance_miles": stop_distance,
            "estimated_hours": total_duration_hours * stop_percentage
        })

    return {
        "from": {
            "name": from_location,
            "coordinates": [from_coords["lon"], from_coords["lat"]]
        },
        "pickup": {
            "name": pickup_location,
            "coordinates": [pickup_coords["lon"], pickup_coords["lat"]]
        },
        "dropoff": {
            "name": to_location,
            "coordinates": [to_coords["lon"], to_coords["lat"]]
        },
        "distance_miles": total_distance_miles,
        "duration_hours": total_duration_hours,
        "geometry": combined_geometry,
        "fuel_stops": fuel_stops
    }

def generate_eld_logs(trip, route_data, current_cycle_used):
    """Generate ELD logs based on route and HOS regulations"""
    # Delete existing logs for this trip
    LogEntry.objects.filter(trip=trip).delete()
    FuelStop.objects.filter(trip=trip).delete()

    # Constants for Hours of Service rules
    MAX_DRIVING_TIME = 11  # hours
    MAX_ON_DUTY_TIME = 14  # hours
    REQUIRED_REST_TIME = 10  # hours
    MAX_CYCLE_HOURS = 70  # hours in 8 days

    # Start with current date and time
    current_date = datetime.datetime.now()
    current_time = current_date

    # Set initial available hours based on current cycle used
    available_driving_time = MAX_DRIVING_TIME
    available_on_duty_time = MAX_ON_DUTY_TIME
    available_cycle_time = MAX_CYCLE_HOURS - current_cycle_used

    # Create logs array to store all log entries
    logs = []

    # Helper function to add a log entry
    def add_log_entry(status, start_time, end_time, location, remarks=None):
        log_entry = LogEntry.objects.create(
            trip=trip,
            date=start_time.date(),
            start_time=start_time.time(),
            end_time=end_time.time(),
            status=status,
            location=location,
            remarks=remarks
        )
        logs.append(log_entry)
        return log_entry

    # Calculate pickup time
    # First, drive to pickup location
    # Fix for division by zero error
    total_route_distance = route_data["distance_miles"]
    if total_route_distance <= 0:
        # Handle case where distance is zero or negative
        driving_to_pickup_hours = 0
    else:
        # Calculate ratio for pickup leg
        pickup_ratio = 1.0
        if route_data["fuel_stops"]:
            # If there are fuel stops, calculate ratio based on last fuel stop distance
            total_with_fuel = total_route_distance
            pickup_ratio = total_route_distance / total_with_fuel

        driving_to_pickup_hours = route_data["duration_hours"] * pickup_ratio

    # Check if we need to split driving due to HOS limits
    remaining_driving_hours = driving_to_pickup_hours
    current_location = route_data["from"]["name"]

    while remaining_driving_hours > 0:
        drive_segment = min(remaining_driving_hours, available_driving_time, available_on_duty_time, available_cycle_time)

        # If we can't drive at all, take a rest
        if drive_segment <= 0:
            rest_start = current_time
            rest_end = rest_start + datetime.timedelta(hours=REQUIRED_REST_TIME)

            add_log_entry("OFF_DUTY", rest_start, rest_end, current_location, "Required rest period")

            # Update time and available hours
            current_time = rest_end
            available_driving_time = MAX_DRIVING_TIME
            available_on_duty_time = MAX_ON_DUTY_TIME
            # Cycle time doesn't reset here
            continue

        # Log driving time
        drive_start = current_time
        drive_end = drive_start + datetime.timedelta(hours=drive_segment)

        add_log_entry("DRIVING", drive_start, drive_end, current_location,
                     f"Driving to {route_data['pickup']['name']}")

        # Update available hours and remaining driving
        available_driving_time -= drive_segment
        available_on_duty_time -= drive_segment
        available_cycle_time -= drive_segment
        remaining_driving_hours -= drive_segment
        current_time = drive_end

        # Approximate current location after this driving segment
        # (This is a simplified approximation)
        current_location = f"En route to {route_data['pickup']['name']}"

    # Now at pickup location
    current_location = route_data['pickup']['name']

    # 1 hour for pickup (on-duty, not driving)
    pickup_start = current_time
    pickup_end = pickup_start + datetime.timedelta(hours=1)

    # Check if we need to rest before pickup
    if available_on_duty_time < 1:
        rest_start = current_time
        rest_end = rest_start + datetime.timedelta(hours=REQUIRED_REST_TIME)

        add_log_entry("OFF_DUTY", rest_start, rest_end, current_location, "Required rest before pickup")

        current_time = rest_end
        available_driving_time = MAX_DRIVING_TIME
        available_on_duty_time = MAX_ON_DUTY_TIME

        # Update pickup times
        pickup_start = current_time
        pickup_end = pickup_start + datetime.timedelta(hours=1)

    add_log_entry("ON_DUTY", pickup_start, pickup_end, current_location, "Loading cargo")

    # Update available hours
    available_on_duty_time -= 1
    available_cycle_time -= 1
    current_time = pickup_end

    # Now drive to dropoff location
    driving_to_dropoff_hours = route_data["duration_hours"] - driving_to_pickup_hours

    # Handle fuel stops
    for i, fuel_stop in enumerate(route_data["fuel_stops"]):
        # Calculate driving time to this fuel stop
        if i == 0:
            driving_hours_to_stop = fuel_stop["estimated_hours"] - driving_to_pickup_hours
        else:
            driving_hours_to_stop = fuel_stop["estimated_hours"] - route_data["fuel_stops"][i-1]["estimated_hours"]

        # Same pattern: check if we need to split driving due to HOS limits
        remaining_driving_hours = driving_hours_to_stop

        while remaining_driving_hours > 0:
            drive_segment = min(remaining_driving_hours, available_driving_time, available_on_duty_time, available_cycle_time)

            # If we can't drive at all, take a rest
            if drive_segment <= 0:
                rest_start = current_time
                rest_end = rest_start + datetime.timedelta(hours=REQUIRED_REST_TIME)

                add_log_entry("OFF_DUTY", rest_start, rest_end, current_location, "Required rest period")

                current_time = rest_end
                available_driving_time = MAX_DRIVING_TIME
                available_on_duty_time = MAX_ON_DUTY_TIME
                continue

            # Log driving time
            drive_start = current_time
            drive_end = drive_start + datetime.timedelta(hours=drive_segment)

            add_log_entry("DRIVING", drive_start, drive_end, current_location,
                         f"Driving to fuel stop")

            # Update available hours and remaining driving
            available_driving_time -= drive_segment
            available_on_duty_time -= drive_segment
            available_cycle_time -= drive_segment
            remaining_driving_hours -= drive_segment
            current_time = drive_end

            # Update approximate location
            current_location = f"En route to fuel stop"

        # At fuel stop
        # Update location to coordinate-based location (simplified)
        fuel_stop_coords = fuel_stop["coordinates"]
        current_location = f"Fuel stop near {fuel_stop_coords[1]:.4f}, {fuel_stop_coords[0]:.4f}"

        # Save fuel stop
        FuelStop.objects.create(
            trip=trip,
            location=current_location,
            estimated_time=current_time
        )

        # 30 minutes for fueling (on-duty, not driving)
        fuel_start = current_time
        fuel_end = fuel_start + datetime.timedelta(minutes=30)

        # Check if we need to rest before fueling
        if available_on_duty_time < 0.5:
            rest_start = current_time
            rest_end = rest_start + datetime.timedelta(hours=REQUIRED_REST_TIME)

            add_log_entry("OFF_DUTY", rest_start, rest_end, current_location, "Required rest before fueling")

            current_time = rest_end
            available_driving_time = MAX_DRIVING_TIME
            available_on_duty_time = MAX_ON_DUTY_TIME

            # Update fueling times
            fuel_start = current_time
            fuel_end = fuel_start + datetime.timedelta(minutes=30)

        add_log_entry("ON_DUTY", fuel_start, fuel_end, current_location, "Refueling")

        # Update available hours
        available_on_duty_time -= 0.5
        available_cycle_time -= 0.5
        current_time = fuel_end

    # Final leg to dropoff
    if route_data["fuel_stops"]:
        last_fuel_stop = route_data["fuel_stops"][-1]
        remaining_driving_hours = route_data["duration_hours"] - last_fuel_stop["estimated_hours"]
    else:
        remaining_driving_hours = driving_to_dropoff_hours

    # Same driving pattern as before
    while remaining_driving_hours > 0:
        drive_segment = min(remaining_driving_hours, available_driving_time, available_on_duty_time, available_cycle_time)

        # If we can't drive at all, take a rest
        if drive_segment <= 0:
            rest_start = current_time
            rest_end = rest_start + datetime.timedelta(hours=REQUIRED_REST_TIME)

            add_log_entry("OFF_DUTY", rest_start, rest_end, current_location, "Required rest period")

            current_time = rest_end
            available_driving_time = MAX_DRIVING_TIME
            available_on_duty_time = MAX_ON_DUTY_TIME
            continue

        # Log driving time
        drive_start = current_time
        drive_end = drive_start + datetime.timedelta(hours=drive_segment)

        add_log_entry("DRIVING", drive_start, drive_end, current_location,
                     f"Driving to {route_data['dropoff']['name']}")

        # Update available hours and remaining driving
        available_driving_time -= drive_segment
        available_on_duty_time -= drive_segment
        available_cycle_time -= drive_segment
        remaining_driving_hours -= drive_segment
        current_time = drive_end

        # Update approximate location
        current_location = f"En route to {route_data['dropoff']['name']}"

    # Now at dropoff location
    current_location = route_data['dropoff']['name']

    # 1 hour for dropoff (on-duty, not driving)
    dropoff_start = current_time
    dropoff_end = dropoff_start + datetime.timedelta(hours=1)

    # Check if we need to rest before dropoff
    if available_on_duty_time < 1:
        rest_start = current_time
        rest_end = rest_start + datetime.timedelta(hours=REQUIRED_REST_TIME)

        add_log_entry("OFF_DUTY", rest_start, rest_end, current_location, "Required rest before unloading")

        current_time = rest_end
        available_driving_time = MAX_DRIVING_TIME
        available_on_duty_time = MAX_ON_DUTY_TIME

        # Update dropoff times
        dropoff_start = current_time
        dropoff_end = dropoff_start + datetime.timedelta(hours=1)

    add_log_entry("ON_DUTY", dropoff_start, dropoff_end, current_location, "Unloading cargo")

    # Update available hours
    available_on_duty_time -= 1
    available_cycle_time -= 1
    current_time = dropoff_end

    # Final off-duty period
    off_duty_start = current_time
    off_duty_end = off_duty_start + datetime.timedelta(hours=1)

    add_log_entry("OFF_DUTY", off_duty_start, off_duty_end, current_location, "End of trip")

    return logs