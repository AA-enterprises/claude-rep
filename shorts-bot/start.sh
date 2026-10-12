#!/usr/bin/env bash
cd "$(dirname "$0")"
python3 bot.py --update --quiet
python3 bot.py --ask
