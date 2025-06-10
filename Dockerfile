FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Устанавливаем права на все Python-файлы
RUN chmod 644 *.py && \
    chmod 644 config.py

CMD ["python", "bot.py"]
