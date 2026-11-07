#!/bin/sh
set -eu

user=$1
[ -n "$user" ] || exit 2
command -v setfacl >/dev/null 2>&1 || exit 3

count=0
for device in /dev/input/event*; do
    [ -e "$device" ] || continue
    setfacl -m "u:$user:r" "$device"
    count=$((count + 1))
done
[ "$count" -gt 0 ] || exit 4
