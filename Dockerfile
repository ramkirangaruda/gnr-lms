FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN DJANGO_DEBUG=0 python manage.py collectstatic --noinput
EXPOSE 8000
# gthread workers handle many concurrent users well; tune WEB_CONCURRENCY to 2 x CPU cores + 1.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-5} --threads 4 --worker-class gthread --timeout 120 --max-requests 2000 --max-requests-jitter 200 --access-logfile -"]
