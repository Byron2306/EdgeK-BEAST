FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV BEAST_DIO_WITNESS_ENABLE_DOCS=0

WORKDIR /app

COPY requirements.commons-node.txt /app/requirements.commons-node.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /app/requirements.commons-node.txt uvicorn

COPY app /app/app

EXPOSE 7860

CMD ["uvicorn", "app.dio_hf_witness_main:app", "--host", "0.0.0.0", "--port", "7860"]
