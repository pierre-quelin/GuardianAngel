FROM python:3-alpine

WORKDIR /usr/src/app

# Update packages and install git
# Clone the repository
# Install Python requirements
RUN apk update && apk add --no-cache git && \
    git clone https://github.com/pierre-quelin/GuardianAngel.git . && \
    pip install --no-cache-dir -r requirements.txt

# Create a non-root user and switch to it
RUN adduser -D appuser
USER appuser

# Command to be executed when the container starts
CMD ["python", "main.py"]
