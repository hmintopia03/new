# Uptime Monitor

A simple uptime monitoring service built with FastAPI, PostgreSQL, Docker, and Discord alerts.

## Current Features

- FastAPI backend
- PostgreSQL database
- Dockerfile deployment
- Railway cloud deployment
- Periodic uptime checks
- Target CRUD
- Duplicate URL prevention
- Healthcheck endpoint
- Basic stats API
- Target-specific stats API
- Discord alert support

## Tech Stack

- Python
- FastAPI
- SQLAlchemy
- PostgreSQL
- Docker
- APScheduler
- Discord Webhook

## API Endpoints

- `GET /`
- `GET /health`
- `POST /targets`
- `GET /targets`
- `PUT /targets/{target_id}`
- `DELETE /targets/{target_id}`
- `POST /check`
- `GET /checks`
- `GET /stats`
- `GET /targets/{target_id}/stats`

## Run Locally

```bash
docker compose up --build
