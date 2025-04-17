FROM python:3-alpine

WORKDIR /usr/src/app

# TODO - COPY . .
RUN git clone https://github.com/pierre-quelin/GuardianAngel.git .

# Installing dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create a non-root user and switch to it
RUN useradd -m appuser
USER appuser

# Command to be executed when the container starts
CMD ["python", "main.py"]
