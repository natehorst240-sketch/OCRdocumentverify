# Aviation Maintenance Records Processor — app image.
# Bundles the Streamlit app and its native OCR/PDF dependencies. The LLM runs
# in a separate Ollama container (see docker-compose.yml).
FROM python:3.11-slim

# System libraries required by the Python stack:
#   poppler-utils  -> pdf2image (PDF rasterization)
#   libgl1, libglib2.0-0 -> OpenCV
#   libgomp1       -> PaddleOCR / PaddlePaddle
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so they cache across code changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# State directories (bind-mounted to the host in compose for persistence).
RUN mkdir -p uploads output templates

EXPOSE 8501

# Container is healthy once Streamlit's internal health endpoint responds.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", \
     "--server.headless=true"]
