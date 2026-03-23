FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY .env.example .

RUN mkdir -p /data/sandbox

ENV FILE_MANAGER_SANDBOX=/data/sandbox
ENV FILE_MANAGER_HOST=0.0.0.0
ENV FILE_MANAGER_PORT=8000

EXPOSE 8000

CMD ["python", "server.py"]
