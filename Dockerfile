FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Создаём папку data (если не существует)
RUN mkdir -p data

# Устанавливаем права на все Python-файлы
RUN chmod 644 *.py && \
    chmod 644 config.py

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Clone resource repositories (shallow)
RUN git clone --depth 1 --branch master https://github.com/Mar-7th/StarRailRes.git StarRailRes-master \
    && git clone --depth 1 --branch main https://github.com/fribbels/hsr-optimizer.git hsr-optimizer-main
    
RUN python prepare_assets.py

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
