FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy the requirements files
COPY requirements.txt requirements-dev.txt ./

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY src/ ./src/
COPY scripts/ ./scripts/

# Set the entry point for the application
ENTRYPOINT ["python", "./src/content_collector/cli/main.py"]