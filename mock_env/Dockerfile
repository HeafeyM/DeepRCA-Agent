FROM python:3.11-slim

WORKDIR /app

COPY requirements-mock.txt .
RUN pip install --no-cache-dir -r requirements-mock.txt

COPY mock_env/ /app/mock_env/
ENV PYTHONPATH=/app

EXPOSE 8001 8002 8003 8004

CMD ["python", "-m", "mock_env.main"]
