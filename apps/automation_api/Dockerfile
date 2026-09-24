FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY apps/automation_api/src ./apps/automation_api/src

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "automation_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
