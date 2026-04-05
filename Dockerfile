FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY pyproject.toml .

RUN pip install -e .

EXPOSE 8765

ENV PYTHONUNBUFFERED=1

CMD ["opencode-telegram"]
