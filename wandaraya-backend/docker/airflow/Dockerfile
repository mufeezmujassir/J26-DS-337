FROM apache/airflow:3.0.4
USER root
RUN apt-get update && apt-get install -y \
    g++ \
    curl \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY docker/airflow/requirements-airflow.txt /requirements-airflow.txt
USER airflow
RUN pip install --no-cache-dir -r /requirements-airflow.txt