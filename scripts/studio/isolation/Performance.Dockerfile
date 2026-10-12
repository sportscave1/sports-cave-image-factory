FROM sports-cave-studio-runtime:v6-e16f6570@sha256:ac2dd9a18cee4dc26b2ecb702f1f5c14d8c8b5ed81574c2631bbc895fd4f0f29
COPY controller.py /opt/studio/controller.py
USER 65532:65532
