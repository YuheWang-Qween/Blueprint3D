FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY webapp ./webapp
COPY examples/user-floorplan-2026-11-06 ./examples/user-floorplan-2026-11-06
RUN useradd --create-home --uid 10001 blueprint && mkdir /data && chown blueprint /data
USER blueprint
ENV BLUEPRINT_DATA_DIR=/data/blueprint3d
EXPOSE 5000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/healthz',timeout=3)"
CMD ["python", "-m", "uvicorn", "webapp.app:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "1"]
