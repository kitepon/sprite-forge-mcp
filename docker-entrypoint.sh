#!/bin/sh
set -eu

mkdir -p /root/.ssh
cp -R /run/ssh/. /root/.ssh/
chown -R root:root /root/.ssh
chmod 700 /root/.ssh
find /root/.ssh -type f -exec chmod 600 {} +

exec "$@"
