#!/bin/sh
set -eu

python pipelines/product/materialize_deployment_release.py
exec uvicorn goatlab.product.api:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips "${GOATLAB_FORWARDED_ALLOW_IPS:-127.0.0.1}"
