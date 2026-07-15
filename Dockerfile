# Backend API only - the Vue frontend is a static build, deployed separately (e.g. S3 + CloudFront),
# not part of this image. Pushed to ECR and run on an EC2 instance via CI (see
# .github/workflows/ci.yml's deploy job and README's Deployment section for the one-time setup).

FROM python:3.12-slim

# mysqlclient compiles against MySQL's client library at install time - not present on the slim
# base image. build-essential/pkg-config are only needed during `pip install`, but keeping them
# in the final image is a deliberate size-vs-simplicity tradeoff (a multi-stage build would trim
# this, at the cost of real complexity for an app this size).
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DJANGO_SETTINGS_MODULE=settings.production
EXPOSE 8000

# collectstatic and migrate both need real settings/.env values (SECRET_KEY, ALLOWED_HOSTS, a
# real DATABASE_URL) that only exist at container *runtime* on App Runner (injected as env vars),
# not at `docker build` time - so both run here, on every container start, rather than as a
# build step. migrate is safe to run on every start (Django migrations are idempotent); running
# collectstatic every start is a few seconds of overhead in exchange for never risking stale
# static assets from an old image layer.
CMD python manage.py collectstatic --noinput && \
    python manage.py migrate --noinput && \
    gunicorn silverlake.wsgi --bind 0.0.0.0:8000 --workers 3 --log-file -
