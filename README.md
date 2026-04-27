# Uptime Monitor

A simple uptime monitoring service built with FastAPI, PostgreSQL, Docker, and Discord alerts.

## Features

- Register URLs to monitor
- Periodic uptime checks
- Store check results in PostgreSQL
- Track UP / DOWN status
- Basic stats endpoint
- Docker Compose setup
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
- `POST /targets`
- `GET /targets`
- `POST /check`
- `GET /checks`
- `GET /stats`
- `GET /targets/{target_id}/stats`

## Run Locally

```bash
docker compose up --build
