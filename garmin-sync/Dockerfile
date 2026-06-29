FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends jq \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml /app/
COPY garmin_health_data/ /app/garmin_health_data/

RUN pip install --no-cache-dir -e ".[postgres]"

COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
