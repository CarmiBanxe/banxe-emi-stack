# Keycloak 26.2.5 — pre-built image for banxe-emi realm
# ADR-017 / ADR-022 / I-34 / I-35 | FCA CASS 15
#
# WHY a custom Dockerfile instead of the upstream image directly:
#
# KC 26.x uses Quarkus. On first `start` (without --optimized), KC runs
# `kc.sh build` inside the container to compile DB + health + metrics config
# into a native Quarkus executable. This build step spawns a JVM with
# -XX:InitialRAMPercentage=50 — on a 30GB host, that is ~15GB committed
# heap. Docker mem_limit=2g caps the container cgroup, but the build
# process is killed by the user.slice cgroup OOM killer (oom_kill counter
# visible at /sys/fs/cgroup/user.slice/memory.events), not by Docker itself
# (OOMKilled: false). exit 137 (SIGKILL), no dmesg entry.
#
# Fix: move kc.sh build to Docker image build time (docker compose build).
# Docker build runs outside the user.slice cgroup — no OOM constraint.
# The resulting image starts with `start --optimized` (no rebuild at
# container startup), so the JVM goes straight into KC server mode.
#
# Build-time options baked here (cannot be overridden at runtime with --optimized):
#   KC_DB=postgres         — switches DB driver from default dev-file to PostgreSQL
#   KC_HEALTH_ENABLED=true — enables /health/* endpoints
#   KC_METRICS_ENABLED=true — enables /metrics endpoint
#
# Runtime options (still in docker-compose.yml environment section):
#   KC_DB_URL, KC_DB_USERNAME, KC_DB_PASSWORD — connection details (operator-supplied)
#   KC_BOOTSTRAP_ADMIN_*  — admin credentials (operator-supplied)
#   KC_HOSTNAME, KC_LOG_LEVEL — runtime tunables

FROM quay.io/keycloak/keycloak:26.2.5

ENV KC_DB=postgres
ENV KC_HEALTH_ENABLED=true
ENV KC_METRICS_ENABLED=true

RUN /opt/keycloak/bin/kc.sh build
