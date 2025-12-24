# Docker Setup

## Quick Start

```bash
docker compose up -d
```

Open http://localhost:9090

## Cloud Mode Setup

For cloud mode (Tesla Owners API), you need `.pypowerwall.auth` and `.pypowerwall.site` files:

1. Run pypowerwall setup on your host machine first:
```bash
pip install pypowerwall
python -m pypowerwall setup
```

2. Copy the generated files to the project directory:
```bash
cp ~/.pypowerwall.auth .
cp ~/.pypowerwall.site .
```

3. Create your config:
```bash
cp config.yaml.example config.yaml
# Edit config.yaml - set mode: cloud and your email
```

4. Start the container:
```bash
docker compose up -d
```

## Files

The container mounts these from the host:

| File | Purpose |
|------|---------|
| `config.yaml` | Application configuration |
| `data/` | Parquet data files (persisted) |
| `.pypowerwall.auth` | Tesla auth tokens (cloud modes) |
| `.pypowerwall.site` | Site selection (cloud modes) |

## Commands

```bash
# Start
docker compose up -d

# Stop
docker compose down

# View logs
docker compose logs -f

# Rebuild after code changes
docker compose up -d --build

# Shell access
docker compose exec powerwall-controller /bin/bash
```

## Troubleshooting

**Port 9090 already in use:**
```bash
# Check what's using the port
lsof -i :9090

# Stop old containers
docker ps -a
docker stop <container_id>
docker rm <container_id>
```

**Files not mounted:**
- Ensure files exist in the project directory before starting
- Always use `docker compose` commands, not `docker run`
- Rebuild with `docker compose up -d --build`
