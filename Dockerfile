FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Initialize submodules (shallow)
RUN git submodule update --init --depth 1

# Установка браузеров Playwright
RUN python -m playwright install --with-deps

# Создаём папку data (если не существует)
RUN mkdir -p data

# Устанавливаем права на все Python-файлы
RUN chmod 644 *.py && \
    chmod 644 config.py

RUN python prepare_assets.py

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
