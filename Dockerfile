FROM python:3.12-slim

WORKDIR /app

# Install build dependencies for packages that need compilation (e.g., pyarrow, duckdb)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Remove build dependencies to reduce image size
RUN apt-get purge -y gcc g++ && apt-get autoremove -y

COPY app/ ./app/
COPY run.py .

EXPOSE 9090

CMD ["python", "run.py"]
