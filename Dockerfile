# Установка зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование файлов
COPY . .

# (Удалите или закомментируйте строку ниже)
# RUN python -m playwright install --with-deps

# Создаём папку data (если не существует)
