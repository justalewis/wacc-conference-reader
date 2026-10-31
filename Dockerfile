# WAC Clearinghouse conference archives reader (selector, /cccc, /iwac, /cw, /cptsc, /ccw). Deploy with fly.toml.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY wsgi.py ./
COPY selector ./selector
COPY cccc ./cccc
COPY iwac ./iwac
COPY cw ./cw
COPY cptsc ./cptsc
COPY ccw ./ccw
COPY data ./data
ENV PORT=8080
EXPOSE 8080
CMD waitress-serve --listen=0.0.0.0:$PORT --threads=4 wsgi:application
