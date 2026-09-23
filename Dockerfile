FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir
COPY week3 ./week3
EXPOSE 8000
CMD ["uvicorn", "week3.main:app", "--host", "0.0.0.0"]
