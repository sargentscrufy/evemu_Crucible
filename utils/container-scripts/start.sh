#!/bin/bash

echo "Initializing EVEmu..."

#Initialize the database
/src/utils/container-scripts/db_init.sh

#Initialize configuration files
if [ ! -f "/app/etc/eve-server.xml" ]; then
    echo "eve-server.xml not found, installing..."
    cp /src/utils/config/eve-server.xml /app/etc/
fi
if [ ! -f "/app/etc/log.ini" ]; then
    echo "log.ini not found, installing..."
    cp /src/utils/config/log.ini /app/etc/
fi
if [ ! -f "/app/etc/MarketBot.xml" ]; then
    echo "MarketBot.xml not found, installing..."
    cp /src/utils/config/MarketBot.xml /app/etc/
fi
if [ ! -f "/app/etc/devtools.raw" ]; then
    echo "devtools.raw not found, installing..."
    cp /src/utils/config/devtools.raw /app/etc/
fi

#Start eve-server
echo "Starting eve-server..."
cd /app/bin/
# OPS-3: crash backtraces also go to the persistent server_cache volume --
# stdout-only traces were destroyed whenever the container was RECREATED
# (docker logs die with the container), which lost two live crash traces.
# gdb's logging captures only its own console output (the backtraces), not
# the server's stdout, so the crash files stay small.
mkdir -p /app/server_cache/crash
if [ "$RUN_WITH_GDB" == "TRUE" ]; then
    echo "=== Running EVEmu with gdb (batch backtrace on crash) ==="
    gdb -batch -ex run \
        -ex "set logging file /app/server_cache/crash/bt-$(date +%Y%m%d-%H%M%S).log" \
        -ex "set logging enabled on" \
        -ex "bt full" -ex "thread apply all bt" ./eve-server
else
    echo "=== Running EVEmu normally ==="
    ./eve-server
fi