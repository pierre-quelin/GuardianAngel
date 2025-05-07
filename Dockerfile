FROM python:3-alpine

WORKDIR /usr/src/app

# TODO - COPY . .
# Mettre à jour les paquets et installer git
RUN apk update && apk add --no-cache git
RUN git clone https://github.com/pierre-quelin/GuardianAngel.git .

# Installing dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create a non-root user and switch to it
RUN adduser -D appuser
USER appuser

# Command to be executed when the container starts
CMD ["python", "main.py"]
