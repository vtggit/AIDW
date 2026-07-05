# Hardening (#122): upstream's official non-root nginx — master runs as uid 101,
# listens on 8080, pid/cache under /tmp (read-only-rootfs ready).
FROM nginxinc/nginx-unprivileged:1.25-alpine@sha256:8265b1df5a89cc1a0a067e472bf47aca7cee52f0561c98a0dff91312dcdd8adb

# Copy static frontend files into nginx document root
COPY . /usr/share/nginx/html

# Use custom nginx config that sets API base from env
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

# Explicit non-root (uid 101 = nginx in the unprivileged base)
USER 101
