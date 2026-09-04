# Derived from aws-samples/sample-playwright-cli-browser-agent-on-bedrock-agentcore
# commit 0c04fb491cd981db464618108bfb770d0f41a0ad (MIT-0).
FROM public.ecr.aws/docker/library/python:3.13-slim@sha256:a0779d7c12fc20be6ec6b4ddc901a4fd7657b8a6bc9def9d3fde89ed5efe0a3d

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN npm install -g @playwright/cli@0.1.18
RUN pip install --no-cache-dir bedrock-agentcore==1.22.0 boto3==1.43.82

WORKDIR /app

RUN playwright-cli install --skills && \
    mkdir -p .agents/skills && \
    cp -r .claude/skills/playwright-cli .agents/skills/playwright-cli && \
    rm -rf .claude

COPY cdp_connect.py /app/cdp_connect.py
COPY attach-browser.sh /app/attach-browser.sh
COPY close-browser.sh /app/close-browser.sh
RUN chmod +x /app/*.sh && useradd --create-home appuser

USER appuser
HEALTHCHECK NONE
CMD ["sleep", "infinity"]
