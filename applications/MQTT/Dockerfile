FROM python:3.13

# Add your Python script
ADD mqtt_publisher_service.py .

# Add requirements file
ADD requirements.txt .

# Install requirements
RUN pip install -r requirements.txt

ENTRYPOINT ["python", "/mqtt_publisher_service.py"]