# Same hardened browser/DB runtime; update static metadata parsing only.
# Build script verifies this local tag resolves to the exact original SHA above
# before building. The context contains only this file and page_catalog.py.
FROM sports-cave-speed-preview-base:verified
USER root
COPY psycopg_pool-3.3.3-py3-none-any.whl /opt/studio/psycopg_pool-3.3.3-py3-none-any.whl
RUN echo "9b9cd6a4fcec47a410f7e82d408540e7f77b478509e91b44c1a5457a13e5ff37  /opt/studio/psycopg_pool-3.3.3-py3-none-any.whl" | sha256sum -c - && python -m pip install --no-index --no-deps /opt/studio/psycopg_pool-3.3.3-py3-none-any.whl && rm /opt/studio/psycopg_pool-3.3.3-py3-none-any.whl
COPY page_catalog.py /opt/studio/page_catalog.py
USER 65532:65532
