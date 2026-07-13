FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

COPY src/ /app/src/
COPY tests/ /app/tests/
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/src

CMD ["python", "-m", "pytest", "tests/smoke/", "-v", "--tb=short"]
