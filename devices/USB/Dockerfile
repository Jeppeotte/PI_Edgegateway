FROM python:3.13-slim

RUN apt-get update && \
    apt-get install -y libportaudio2 alsa-utils && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Add main service
COPY devices/USB/USB_microphone_service.py .

# Add local dependencies
COPY models/devicemodels.py ./models/devicemodels.py

# Add requirements
COPY devices/USB/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["python", "USB_microphone_service.py"]
