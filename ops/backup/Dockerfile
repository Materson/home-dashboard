# Nightly encrypted backup of the database and the uploaded files, plus
# `backup-now` and `restore <file>` for Portainer's console.
FROM alpine:3.20
RUN apk add --no-cache mariadb-client gnupg tar coreutils findutils tzdata
COPY entrypoint.sh /ops/entrypoint.sh
COPY restore.sh /usr/local/bin/restore
RUN printf '#!/bin/sh\nexec /bin/sh /ops/entrypoint.sh now\n' > /usr/local/bin/backup-now \
    && chmod +x /usr/local/bin/backup-now /usr/local/bin/restore
ENTRYPOINT ["/bin/sh", "/ops/entrypoint.sh"]
