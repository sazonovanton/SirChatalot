#################################################
#         Dockerfile to run SirChatalot         #
#################################################

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

# ffmpeg — voice messages; catdoc (includes catppt) — legacy .doc/.ppt conversion
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    catdoc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Uncomment to run stdio MCP servers distributed via npm (npx ...):
# RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
#     && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install dependencies first so code changes don't invalidate this layer
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python3", "main.py"]
