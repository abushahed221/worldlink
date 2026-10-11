#!/usr/bin/env bash
set -o errexit

echo "=========== Installing dependencies ==========="
pip install --upgrade pip
pip install -r requirements.txt

echo "=========== Compiling translations ==========="
python manage.py compilemessages || echo "⚠️ compilemessages skipped (gettext not installed on server)"

echo "=========== Collecting static files ==========="
python manage.py collectstatic --no-input --clear

echo "=========== Running migrations ==========="
python manage.py migrate --no-input

echo "=========== Deployment build complete ==========="