FROM python:3.11-slim

# Установка зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование файлов
COPY . .

# Создаём папку data (если не существует)
RUN mkdir -p data

CMD ["python", "bot.py"]
