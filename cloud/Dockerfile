# Build from the repo root:  docker build -f cloud/Dockerfile -t hey-cindy-cloud .
FROM python:3.12-slim

WORKDIR /app

COPY cloud/requirements.txt ./cloud/requirements.txt
RUN pip install --no-cache-dir -r cloud/requirements.txt

COPY cloud/ ./cloud/

EXPOSE 8000

CMD ["uvicorn", "cloud.app:app", "--host", "0.0.0.0", "--port", "8000"]
