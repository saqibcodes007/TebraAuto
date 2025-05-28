# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /app
# Make sure your .dockerignore file excludes .venv, __pycache__, etc.
COPY . .

# Make port 5000 available to the world outside this container
# This MUST match the --bind port and your Azure Ingress Target Port
EXPOSE 5000

# Define environment variable for Gunicorn timeout (e.g., 5 minutes)
# You can also set this in Azure Container App configuration
ENV GUNICORN_TIMEOUT 300

# Run gunicorn when the container launches
# It will look for an 'app' instance in a file named 'main.py'.
# Change the port in --bind to 5000
CMD ["gunicorn", "--workers", "1", "--timeout", "$GUNICORN_TIMEOUT", "--bind", "0.0.0.0:5000", "main:app"]
