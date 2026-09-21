#!/bin/sh
set -eu

python pipelines/product/materialize_deployment_release.py
python pipelines/product/migrate_product_database.py
python pipelines/product/load_ranking_release.py --release-dir "${GOATLAB_PRODUCT_ARTIFACT_ROOT:?}/${GOATLAB_RELEASE_ID:?}"
