FROM python:3.13-slim

WORKDIR /app

# Add main service
COPY devices/S7Comm/S7Comm_service.py .

# Add local dependencies
COPY models/devicemodels.py ./models/devicemodels.py

# Add requirements
COPY devices/S7Comm/requirements.txt .

RUN pip install -r requirements.txt

ENTRYPOINT ["python", "S7Comm_service.py"]
