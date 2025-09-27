FROM python:3.13-slim
WORKDIR /app
COPY app.py .
RUN pip install flask
CMD ["python", "app.py", "--host=0.0.0.0"]
