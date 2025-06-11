FROM python:3.11-slim

# Копируем только requirements.txt для установки зависимостей
COPY requirements.txt .

# Установка зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальные файлы проекта
COPY . .

# Создаём папку data (если не существует)
RUN mkdir -p data

CMD ["python", "bot.py"]
