FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy engine source and shared models
COPY engine/ .
COPY shared/ ./shared/

CMD ["python", "main.py"]
