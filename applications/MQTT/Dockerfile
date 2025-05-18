FROM python:3.13-slim

# Add your Python script
COPY applications/MQTT/mqtt_publisher.yaml .

COPY applications/MQTT/mqtt_publisher_service.py .

# Add requirements file
COPY applications/MQTT/requirements.txt .

# Install requirements
RUN pip install -r requirements.txt

ENTRYPOINT ["python", "/mqtt_publisher_service.py"]