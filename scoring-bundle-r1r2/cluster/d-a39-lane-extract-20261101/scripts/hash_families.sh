#!/bin/bash
O=<FORECAST_ROOT>/d-a39-lane-extract-20261101
D=<FORECAST_ROOT>/data-custodian/single-R2-v1/arms/000/rescore-secondary-D-A39
cd /tmp || exit 9
stat -c "%n %s %F %Y" "$D"/families/* "$D"/secondary-result* "$D"/*.json > "$O/out/stat.txt"
sha256sum "$D"/families/*.part0000 "$D"/families/*.manifest.json "$D"/secondary-result-raw.pkl.part0000 "$D"/primary-recomputed-D-A39.json "$D"/second-label-read-D-A39.json "$D"/completion.json "$D"/intent.json > "$O/out/sha256-small.txt" 2>&1
sha256sum "$D"/secondary-result.json > "$O/out/sha256-secondary-json.txt" 2>&1
echo done > "$O/out/hash.done"
