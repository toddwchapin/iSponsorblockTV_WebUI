# builder: installs this repo's own source (pip install .), not a git+https
# fetch of itself - this Dockerfile lives inside the project it packages,
# so the source is already on disk. No git needed in this stage.
FROM python:3.12-slim AS builder
WORKDIR /src
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir --prefix=/install .

# The app's own restart/status/log-tail detection (app/services/restart.py,
# service_status.py) hardcodes a check for /var/run/docker.sock and shells
# out to the real `docker` binary - it has no HTTP-API path, so it can't be
# pointed at docker-socket-proxy. Pulled from the official docker:cli image
# purely for the static binary, not the daemon.
FROM docker:27-cli AS dockercli

FROM python:3.12-slim
COPY --from=builder /install /usr/local
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker

EXPOSE 8099
ENTRYPOINT ["isponsorblocktv-webui"]
