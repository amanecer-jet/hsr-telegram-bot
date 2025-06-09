FROM python:3.11-slim

# Установка зависимостей для Chromium и Python
RUN apt-get update && \
    apt-get install -y wget gnupg2 curl unzip \
    chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Установка зависимостей Python
WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Копируем код бота
COPY . .

# Переменные окружения для Selenium
ENV PATH="/usr/lib/chromium/:${PATH}"
ENV CHROME_BIN="/usr/bin/chromium"
ENV CHROMEDRIVER_PATH="/usr/bin/chromedriver"

# Запуск приложения
CMD ["python", "bot.py"] 