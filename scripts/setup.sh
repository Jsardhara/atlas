#!/usr/bin/env bash
# ATLAS Setup Script
set -e

echo "=== ATLAS Setup ==="

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed. Install from https://docker.com"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "ERROR: Docker Compose v2 not found."
    exit 1
fi

# Copy env if missing
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from template — fill in your API keys before starting."
    exit 0
fi

echo "Building images..."
docker compose build

echo "Starting infrastructure..."
docker compose up -d postgres redis

echo "Waiting for postgres..."
sleep 5

echo "Starting all services..."
docker compose up -d

echo ""
echo "=== ATLAS is starting up ==="
echo "Dashboard: http://localhost:80"
echo "API:       http://localhost:8000"
echo ""
echo "To enable remote access, set CF_TUNNEL_TOKEN in .env then:"
echo "  docker compose --profile remote up -d cloudflared"
