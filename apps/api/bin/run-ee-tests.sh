#!/bin/sh
# Run the EE test-suite inside the api-tests container (Alpine). Usage:
#   docker compose -f docker-compose-test.yml run --rm api-tests sh bin/run-ee-tests.sh plane/tests/unit/ee
set -e
apk add --no-cache --virtual .ee-build gcc g++ musl-dev libffi-dev pkgconf xmlsec-dev libxml2-dev libxslt-dev
# lxml and xmlsec must link the same libxml2. lxml is already installed as a wheel (base.txt pin), so a plain
# "--no-binary" install would be a no-op: force-reinstall just these two from source, honoring the project pins.
pip install --no-cache-dir --force-reinstall --no-deps --no-binary lxml,xmlsec -c requirements/base.txt -c requirements/ee.txt lxml xmlsec
pip install --no-cache-dir -c requirements/base.txt -r requirements/ee.txt
# unrelated base.txt conflicts exist (h11, opentelemetry); only fail on ours
if pip check | grep -i -E 'saml|xmlsec|lxml'; then exit 1; fi
exec pytest --ds=plane.settings.ee_test "$@"
