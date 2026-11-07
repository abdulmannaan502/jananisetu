#!/bin/sh
# Evaluator-demo start-up: create the schema, load synthetic data (idempotent), run the API.
# SYNTHETIC DATA ONLY. Used by render.yaml.
set -e
python -c "import app.main"
python -m scripts.seed_demo_data
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
