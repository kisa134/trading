FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY trading_platform/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY trading_platform /app

CMD ["python", "-m", "api.main", "--port", "8000"]
