FROM python:3.12-slim
WORKDIR /app
COPY scripts/studio/stage_host.py /app/stage_host.py
COPY components/developer_studio/panel.html components/developer_studio/panel.css components/developer_studio/panel.js /app/components/developer_studio/
USER 65532:65532
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 10000
CMD ["python", "-B", "/app/stage_host.py"]
