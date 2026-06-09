#!/usr/bin/env bash
# exit on error
set -o errexit

mkdir -p data
pip install -r requirements.txt
python scripts/seed_db.py
