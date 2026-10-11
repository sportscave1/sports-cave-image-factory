FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
RUN apt-get update && apt-get install -y --no-install-recommends postgresql && rm -rf /var/lib/apt/lists/*
COPY requirements.preview.txt /opt/requirements.preview.txt
RUN pip install --no-cache-dir -r /opt/requirements.preview.txt
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
RUN python -m playwright install --with-deps chromium && chmod -R a+rX /opt/browsers
RUN useradd --uid 65532 --no-create-home studio
COPY probe.py browser_probe.py entry.py controller.py /opt/studio/
USER 65532:65532
