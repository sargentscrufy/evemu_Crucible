#!/bin/bash

# This is a script to populate the db container with the sql table data.
# Author: James, Gwen

MARIADB_HOST="${MARIADB_HOST:-db}"
MARIADB_DATABASE="${MARIADB_DATABASE:-evemu}"
MARIADB_PASSWORD="${MARIADB_PASSWORD:-evemu}"
MARIADB_USER="${MARIADB_USER:-evemu}"
MARIADB_PORT="${MARIADB_PORT:-3306}"


# Get script path:
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"

# Function to determine health of MariaDB container
function waitContainer {
    #Checking if we can actually connect to the container
    while ! mysql -h $MARIADB_HOST -u $MARIADB_USER -p$MARIADB_PASSWORD -e "use $MARIADB_DATABASE;show tables;" >/dev/null 2>&1; do
        printf .
        sleep 1
    done
}

# Wait for container to be up and running...
echo "Waiting for DB to start..."
waitContainer evemu_db

#Write the eve-server.xml variables
sed -i "s/database_host/$MARIADB_HOST/" /src/utils/config/eve-server.xml
sed -i "s/database_username/$MARIADB_USER/" /src/utils/config/eve-server.xml
sed -i "s/database_password/$MARIADB_PASSWORD/" /src/utils/config/eve-server.xml
sed -i "s/database_name/$MARIADB_DATABASE/" /src/utils/config/eve-server.xml
sed -i "s/database_port/$MARIADB_PORT/" /src/utils/config/eve-server.xml


# Write evedb.yaml based upon above variables
cd /src/sql
cat >/src/sql/evedb.yaml <<EOF
base-dir: /src/sql/base
db-database: $MARIADB_DATABASE
db-host: $MARIADB_HOST
db-pass: $MARIADB_PASSWORD
db-port: $MARIADB_PORT
db-user: $MARIADB_USER
log-level: Info
migrations-dir: /src/sql/migrations
dungeons-dir: /src/sql/dungeons
EOF

echo "Running EVEDBTool..."
/src/sql/evedbtool install

if [ "$SEED_MARKET" == "TRUE" ]
then
    # Market Seed v2: hub-weighted sell orders + NPC buy walls + price
    # history (sql/seed_and_clean/seed_market_v2.sql). SEED_SATURATION is
    # the % of non-hub stations that get stocked.
    IFS=',' read -r -a array <<< "$SEED_REGIONS"
    {
        echo "USE $MARIADB_DATABASE;"
        echo "SET @saturation = ${SEED_SATURATION:-50} / 100;"
        echo "CREATE TEMPORARY TABLE tSeedRegions (regionName VARCHAR(100));"
        for i in "${array[@]}"
        do
            echo "INSERT INTO tSeedRegions VALUES ('$i');"
        done
        cat /src/sql/seed_and_clean/seed_market_v2.sql
    } | mysql -h $MARIADB_HOST -P $MARIADB_PORT -u $MARIADB_USER -p$MARIADB_PASSWORD
fi

echo "Loading all dungeons using EVEDBTool..."
/src/sql/evedbtool dungeon apply