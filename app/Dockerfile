# Hardening (#122): upstream's official non-root nginx — master runs as uid 101,
# listens on 8080, pid/cache under /tmp (read-only-rootfs ready).
FROM nginxinc/nginx-unprivileged:1.25-alpine@sha256:8265b1df5a89cc1a0a067e472bf47aca7cee52f0561c98a0dff91312dcdd8adb

# Copy the runtime frontend assets into the nginx document root. Deliberately an
# ALLOWLIST, not `COPY .`: the build context also carries nginx.conf and (before
# .dockerignore) the Playwright suite, and `COPY .` published both under the
# public web root — every spec was fetchable at /tests/*.spec.js and the proxy
# topology at /nginx.conf. tests/ is now out of the context (.dockerignore);
# nginx.conf CANNOT be, because the COPY below needs it there, so this allowlist
# is what keeps it out of the web root.
# A new runtime asset directory must be added here. That failure mode is a loud
# 404, not a silent disclosure.
COPY index.html studio.html /usr/share/nginx/html/
COPY css/ /usr/share/nginx/html/css/
COPY js/ /usr/share/nginx/html/js/

# Use custom nginx config that sets API base from env
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

# Explicit non-root (uid 101 = nginx in the unprivileged base)
USER 101
