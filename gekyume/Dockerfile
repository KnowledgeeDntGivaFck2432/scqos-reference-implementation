FROM python:3.14-slim

WORKDIR /app

RUN pip install --no-cache-dir rfc8785

COPY scqos_supreme_stack.py /app/
COPY gekyume /app/gekyume/

ENV PYTHONPATH=/app

CMD ["python", "/app/gekyume/gekyume_core.py"]
