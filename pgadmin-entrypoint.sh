#!/bin/sh

# Stop on first error
set -e

# Create the configuration files as the root user
echo "${PG_HOST}:${PG_PORT}:${PG_DB}:${PG_USER}:${PG_PASSWORD}" > /pgadmin4/pgpass
cat << EOF > /pgadmin4/servers.json
{
    "Servers": {
        "1": {
            "Name": "Docker Postgres DB",
            "Group": "Servers",
            "Host": "${PG_HOST}",
            "Port": ${PG_PORT},
            "MaintenanceDB": "${PG_DB}",
            "Username": "${PG_USER}",
            "PassFile": "/pgadmin4/pgpass",
            "SSLMode": "prefer"
        }
    }
}
EOF

# Set read-only permissions for the files
chmod 600 /pgadmin4/pgpass /pgadmin4/servers.json

# Now, execute the original entrypoint. It will create the 'pgadmin'
# user and fix file ownerships before starting the web server.
exec /entrypoint.sh
