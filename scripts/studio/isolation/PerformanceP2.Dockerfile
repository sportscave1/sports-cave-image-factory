FROM sha256:5a22bde08670c241dd349f56e374ee5510a58f9f13d077831d1cd9de8746d061
USER root
COPY scripts/studio/isolation/controller.py /opt/studio/controller.py
COPY scripts/studio/preview_input.py /opt/studio/preview_input.py
USER 65532
