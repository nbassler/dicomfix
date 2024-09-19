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
RUN pip install .[dev]
RUN pip install .[web]

RUN pytest tests/

# Expose the port that Streamlit will run on
EXPOSE 8501

# Command to run the Streamlit app
CMD ["streamlit", "run", "dicomfix/web/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
