PYTHON ?= python3

.PHONY: test selftest verify lint

test:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest -p no:cacheprovider -q

selftest:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) dai_publication.py selftest

verify:
	@test -n "$(RELEASE)" || (echo "Usage: make verify RELEASE=dist/release.zip TRUSTED_FINGERPRINT=sha256:... EXPECTED_ZIP_SHA256=sha256:..." && exit 2)
	@test -n "$(EXPECTED_ZIP_SHA256)" || (echo "EXPECTED_ZIP_SHA256 is required" && exit 2)
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) dai_evidence.py verify-release "$(RELEASE)" \
		--trusted-fingerprint "$(TRUSTED_FINGERPRINT)" \
		--expected-zip-sha256 "$(EXPECTED_ZIP_SHA256)"

lint:
	$(PYTHON) -m py_compile \
		dai_publication.py dai_publication_core.py dai_evidence.py dai_attack.py dai_ingest.py \
		tests/test_dai_publication.py tests/test_dai_evidence.py \
		tests/test_dai_attack.py tests/test_dai_ingest.py
