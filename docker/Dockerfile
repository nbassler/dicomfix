# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container
COPY ../ /app

# Install any dependencies specified in pyproject.toml
RUN pip install --upgrade pip \
    && pip install .

# Install optional dependencies for web UI (Streamlit)
RUN pip install .[dev,web]

RUN pytest tests/

# Command to run the Streamlit app
# http
# Expose the port that Streamlit will run on
# EXPOSE 8501
# CMD ["streamlit", "run", "dicomfix/web/app.py", "--server.port=8501", "--server.address=0.0.0.0"]

# https if you have the certificate and key files
EXPOSE 8443
CMD ["streamlit", "run", "dicomfix/web/app.py", "--server.port=8443", "--server.address=0.0.0.0", "--server.sslCertFile=${SSL_CERT_FILE}", "--server.sslKeyFile=${SSL_KEY_FILE}"]

