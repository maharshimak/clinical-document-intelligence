FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install .
RUN useradd --uid 10001 --create-home appuser && chown -R appuser:appuser /app
USER appuser
CMD ["python","-c","from clinical_intel.extract import extract; print(extract('Study ID: DEMO-1'))"]
