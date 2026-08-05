PYTHON ?= python3

.PHONY: test selftest verify lint

test:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest -p no:cacheprovider -q

selftest:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) dai_publication.py selftest

verify:
	@test -n "$(RELEASE)" || (echo "Usage: make verify RELEASE=dist/release.zip TRUSTED_FINGERPRINT=sha256:..." && exit 2)
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) dai_publication.py verify "$(RELEASE)" --trusted-fingerprint "$(TRUSTED_FINGERPRINT)"

lint:
	$(PYTHON) -m py_compile dai_publication.py tests/test_dai_publication.py
