FROM sports-cave-studio-runtime:v8-silent-perf-01a13216@sha256:a76ad636607432cf763373e321d1151a1936d2df6f152dbbe01ef4badfa1c3b4
COPY controller.py /opt/studio/controller.py
USER 65532:65532
