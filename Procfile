web: gunicorn --bind 127.0.0.1:8000 union.wsgi --timeout 180 --workers 5 --threads 4 --worker-class gthread --max-requests 1000 --max-requests-jitter 100
worker: celery -A union worker -l info
beat: celery -A union beat -l info --schedule ./celerybeat-schedule --pidfile ./celerybeat.pid
