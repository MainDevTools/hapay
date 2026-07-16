# read-API (§8.10.1). Колектор — окремо в GitHub Actions (collect.yml), не в цьому образі.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x docker-entrypoint.sh

EXPOSE 8080
# DATABASE_URL / BOT_TOKEN — через env/secrets хоста (ніколи в образ). RUN_MIGRATIONS=1 — опц.
ENTRYPOINT ["./docker-entrypoint.sh"]
