FROM ghcr.io/openhands/agent-canvas:1.25.0@sha256:10190cdede885f74853567f4aa44b33de094139a940df75f4b204a2b6df73c57
USER root
COPY patch-codex-acp.py /tmp/patch-codex-acp.py
RUN python /tmp/patch-codex-acp.py && rm /tmp/patch-codex-acp.py
USER openhands
