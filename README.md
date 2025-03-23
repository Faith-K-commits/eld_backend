# ELD Backend

A Django-based backend service for Electronic Logging Device (ELD) systems, providing trip management, log entry generation, and route calculation functionality.

## Features

- Trip management (create, read, update, delete)
- Automatic log entry generation
- Route calculation and optimization
- Geocoding and location services
- Fuel stop tracking
- RESTful API endpoints

## Tech Stack

- Python 3.x
- Django 5.1.7
- Django REST Framework
- PostgreSQL (production) / SQLite (development)
- OpenStreetMap (Nominatim) for geocoding
- OSRM for route calculation
- Gunicorn for production deployment

## Prerequisites

- Python 3.x
- pip (Python package manager)
- Virtual environment (recommended)

## Installation

1. Clone the repository:

```bash
git clone https://github.com/Faith-K-commits/eld_backend
cd eld_backend
```

2. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r reqiurements.txt
```

4. Set up environment variables:
   Create a `.env` file in the root directory with the following variables:

```
DEBUG=True
SECRET_KEY=your-secret-key
DATABASE_URL=your-database-url
```

5. Run migrations:

```bash
python manage.py migrate
```

## Development

To run the development server:

```bash
python manage.py runserver
```

The server will be available at `http://localhost:8000`

## API Endpoints

### Trips

- `POST /api/trips/create/` - Create a new trip
- `PUT /api/trips/{id}/` - Update trip
- `DELETE /api/trips/{id}/` - Delete trip

### Log Entries

- `POST /api/trips/{id}/generate-logs/` - Generate log entries for a trip

## Deployment

The project is configured for deployment on Render.com. The `render.yaml` file contains the deployment configuration.

To deploy:

1. Push your code to a Git repository
2. Connect your repository to Render
3. Render will automatically deploy your application using the configuration in `render.yaml`
