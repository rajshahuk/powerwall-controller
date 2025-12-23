# Powerwall Controller

Web-based controller for Tesla Powerwall. Monitor power flow, view historical data, and automate backup reserve changes based on home power usage.

## Features

- Real-time monitoring of solar, battery, grid, and home power
- Historical data storage (Parquet files, queryable via DuckDB)
- Automation rules to adjust backup reserve based on usage thresholds
- Audit log of all changes

## Connection Modes

Supports 4 connection modes via [pypowerwall](https://github.com/jasonacox/pypowerwall):

- **Local** - Direct LAN access (Powerwall 2/+)
- **FleetAPI** - Official Tesla Fleet API
- **Cloud** - Tesla Owners API
- **TEDAPI** - Local WiFi access (Powerwall 3)

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python run.py
```

Open http://localhost:9090 and configure your Powerwall connection.

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

## Project Structure

```
app/
  api.py              # FastAPI routes
  config.py           # YAML configuration
  main.py             # Application entry point
  services/
    powerwall_service.py   # Powerwall communication
    monitoring_service.py  # Data collection
    storage_service.py     # Parquet/DuckDB storage
    automation_service.py  # Rules engine
  templates/          # Jinja2 HTML templates
  static/             # CSS/JS assets
tests/                # pytest tests
data/                 # Parquet files (created at runtime)
config.yaml           # Configuration file
```
