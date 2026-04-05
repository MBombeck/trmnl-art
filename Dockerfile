FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app + batch generator
COPY app/ app/
COPY generate_batch.py .

# Seed data (Rijksmuseum index + goat gallery) - copied to data dir on first run
COPY data-seed/ /app/data-seed/

# Data directory (mount as volume for persistence)
RUN mkdir -p /app/data /app/data/goat-gallery

EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Berlin

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
