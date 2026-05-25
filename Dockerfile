FROM python:3.10-slim

WORKDIR /backend

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN adduser -u 5678 --disabled-password --gecos "" appuser \
    && chown -R appuser /backend
USER appuser

EXPOSE 8000

# 개발용 (추천)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]