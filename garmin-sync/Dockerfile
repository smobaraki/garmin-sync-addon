FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        jq \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN git clone --depth 1 https://github.com/smobaraki/garmin-health-data.git .

RUN pip install --no-cache-dir -e ".[postgres]"

COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
