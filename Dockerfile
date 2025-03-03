#################################################
#         Dockerfile to run SirChatalot         #
#           Based on an Python Image            #
#################################################

# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory to /app
WORKDIR /app

# Install ffmpeg, catdoc (includes catppt), and other necessary dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    catdoc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# Run the command to start the app
CMD ["python3", "main.py"]