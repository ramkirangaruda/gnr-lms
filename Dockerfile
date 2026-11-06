FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# settings.py refuses to start without a secret key when DEBUG is off, so collectstatic gets a throwaway one.
# The real key only ever comes from .env at runtime.
RUN DJANGO_DEBUG=0 DJANGO_SECRET_KEY=collectstatic-only DJANGO_ALLOWED_HOSTS=localhost python manage.py collectstatic --noinput
# Run as an unprivileged user. /app/media is created here so the named volume inherits this ownership.
RUN useradd --create-home --uid 1000 app && mkdir -p /app/media && chown -R app:app /app/media
USER app
EXPOSE 8000
# gthread workers handle many concurrent users well; tune WEB_CONCURRENCY to 2 x CPU cores + 1.
# No --max-requests: recycling workers under load caused occasional 502s, and memory stayed flat in a 30-min soak.
# --keep-alive 75 is longer than Caddy's 60 s, so Caddy always closes idle connections first.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-5} --threads 4 --worker-class gthread --timeout 120 --keep-alive 75 --access-logfile -"]
