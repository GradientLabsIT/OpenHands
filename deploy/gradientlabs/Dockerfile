ARG BASE_IMAGE=ghcr.io/openhands/agent-canvas:1.26.0@sha256:ce4526401c08b47d74fd0be5ebf97e8219d6a02955cb6710e8cc3335f01291a6
FROM ${BASE_IMAGE} AS frontend-build
USER root
WORKDIR /build
COPY frontend-source.tar.gz /tmp/frontend-source.tar.gz
RUN tar -xzf /tmp/frontend-source.tar.gz -C /build && rm /tmp/frontend-source.tar.gz
RUN node -e 'if (require("./package.json").version !== "1.26.0") throw Error("Frontend source does not match the pinned Canvas release")' && npm ci
COPY patch-model-catalog.py subscription-models.json /tmp/
RUN python /tmp/patch-model-catalog.py --client /build/node_modules/@openhands/typescript-client/dist/models/acp-providers.json
ENV VITE_BASE_PATH=/canvas
RUN npm run build

FROM ${BASE_IMAGE}
USER root
ARG FRONTEND_SOURCE_REVISION=unknown
LABEL org.gradientlabs.frontend-revision=${FRONTEND_SOURCE_REVISION}
RUN npm install --global --prefix /acp-node @agentclientprotocol/claude-agent-acp@0.88.0 @agentclientprotocol/codex-acp@2.1.1 && \
    npm install --prefix /acp-node/lib/node_modules/@agentclientprotocol/claude-agent-acp --save-exact @anthropic-ai/claude-agent-sdk@0.3.295 && \
    npm install --prefix /acp-node/lib/node_modules/@agentclientprotocol/codex-acp --save-exact @openai/codex@0.162.0 && npm cache clean --force
RUN node -e 'for (const [path,version] of [["claude-agent-acp","0.88.0"],["codex-acp","2.1.1"]]) { if (require(`/acp-node/lib/node_modules/@agentclientprotocol/${path}/package.json`).version !== version) throw Error("ACP package version mismatch") }' && \
    test "$(/acp-node/lib/node_modules/@agentclientprotocol/codex-acp/node_modules/.bin/codex --version)" = "codex-cli 0.162.0"
COPY patch-codex-acp.py patch-model-catalog.py subscription-models.json /tmp/
RUN python /tmp/patch-codex-acp.py && python /tmp/patch-model-catalog.py --sdk && rm /tmp/patch-codex-acp.py /tmp/patch-model-catalog.py /tmp/subscription-models.json
RUN rm -rf /opt/agent-canvas/frontend
COPY --from=frontend-build /build/build /opt/agent-canvas/frontend
USER openhands
