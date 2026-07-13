FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ /app/src/
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy entry point
ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["uvicorn", "deeprca.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
