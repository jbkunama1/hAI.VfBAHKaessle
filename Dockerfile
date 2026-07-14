
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1         PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_APP=app.py         FLASK_ENV=production

EXPOSE 1904

CMD ["gunicorn", "-b", "0.0.0.0:1904", "app:app"]
