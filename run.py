#!/usr/bin/env python3
"""Main entry point for Powerwall Controller."""

import sys
import uvicorn

from app.config import config


def main():
    """Run the Powerwall Controller application."""
    print(f"Starting Powerwall Controller on http://{config.server_host}:{config.server_port}")
    print("Press Ctrl+C to stop")

    uvicorn.run(
        "app.main:app",
        host=config.server_host,
        port=config.server_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
