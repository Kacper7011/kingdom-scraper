FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY interface/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy interface source and shared models
COPY interface/ .
COPY shared/ ./shared/

EXPOSE 5000

CMD ["python", "app.py"]
