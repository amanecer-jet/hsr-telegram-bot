FROM python:3.11-slim

WORKDIR /app

# Устанавливаем необходимые системные зависимости для Playwright
RUN apt-get update && apt-get install -y \
    curl \
    gnupg2 \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Playwright и его зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium --with-deps

COPY . .

# Устанавливаем права на все Python-файлы
RUN chmod 644 *.py && \
    chmod 644 config.py

CMD ["python", "bot.py"]
