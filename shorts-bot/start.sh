#!/usr/bin/env bash
cd "$(dirname "$0")"
echo "=============================================="
echo "           SHORTS BOT"
echo "=============================================="
read -r -p "YouTube link paste karein (ya links.txt) aur Enter dabayein: " LINK
[ -z "$LINK" ] && exit 0
python3 bot.py "$LINK"
echo
echo "Shorts 'output' folder mein hain."
