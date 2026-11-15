# Reuse the verified local runtime; no package downloads or heavy installation.
FROM sports-cave-studio-runtime:phase4d-login-369a5c73@sha256:4da7a136b03b779bfde89716822d74eb844bb4a910de90ebf04f0668a077ef63
COPY isolation/entry.py isolation/controller.py isolation/inspection.py page_catalog.py /opt/studio/
USER 65532:65532
