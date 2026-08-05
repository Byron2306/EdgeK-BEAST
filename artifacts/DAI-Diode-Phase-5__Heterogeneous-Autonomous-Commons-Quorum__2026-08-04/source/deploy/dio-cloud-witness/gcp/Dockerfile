FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    google-cloud-storage==3.3.1

COPY main.py /app/main.py

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

LABEL "tee.launch_policy.allow_env_override"="DIO_OUTPUT_BUCKET,DIO_OUTPUT_OBJECT,DIO_PHASE2_EVIDENCE_ROOT"

ENTRYPOINT ["python", "/app/main.py"]
