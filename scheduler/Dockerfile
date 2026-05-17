FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY crontab /etc/cron.d/pipeline-cron
RUN chmod 0644 /etc/cron.d/pipeline-cron
RUN crontab /etc/cron.d/pipeline-cron

RUN touch /var/log/cron.log

CMD ["cron", "-f"]