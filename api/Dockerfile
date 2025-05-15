FROM python:3.13-slim

# Add model dependencies
COPY models/devicemodels.py ./models/devicemodels.py

# Copy all API files
COPY api/*.py ./api/

# Copy requirements
COPY api/requirements.txt .

# Add main Python script
COPY api/main.py .

# Add requirements file
COPY api/requirements.txt .

# Install requirements
RUN pip install -r requirements.txt

ENTRYPOINT ["python", "/main.py"]