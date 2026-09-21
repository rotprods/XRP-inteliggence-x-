PYTHON ?= python
PYTHONPATH := src
COMPARE_BRANCH ?= origin/main

.PHONY: install install-deep demo compile test test-fast test-deep coverage coverage-policy changed-coverage diff-cover-crosscheck lint format-check type security verify manifest manifest-check check-fast quality-evidence api clean wheel reproducible-wheel wheel-smoke sbom audit mutation flake-gate

install:
	$(PYTHON) -m pip install -e '.[dev]'

install-deep:
	$(PYTHON) -m pip install -e '.[dev,deep]'

demo:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m xrp_regime_engine.cli demo --output state/demo

compile:
	$(PYTHON) -m compileall -q src tests scripts

test:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(PYTHONPATH) pytest -q -p no:cacheprovider -m 'not live'

test-fast:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(PYTHONPATH) pytest -q -p no:cacheprovider -m 'not slow and not live'

test-deep:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(PYTHONPATH) pytest -q -p no:cacheprovider -m 'not live'

coverage:
	mkdir -p quality
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(PYTHONPATH) pytest --cov=xrp_regime_engine --cov-branch --cov-report=term-missing --cov-report=json:coverage.json --cov-report=xml:coverage.xml --junitxml=quality/pytest.xml -q -p no:cacheprovider -m 'not live'

coverage-policy: coverage
	$(PYTHON) scripts/check_coverage_policy.py coverage.json --report quality/coverage_policy.json

changed-coverage: coverage
	mkdir -p quality
	$(PYTHON) scripts/check_changed_line_coverage.py coverage.json --base $(COMPARE_BRANCH) --threshold 100 --report quality/diff-coverage.json

diff-cover-crosscheck: coverage
	mkdir -p quality
	diff-cover coverage.xml --compare-branch=$(COMPARE_BRANCH) --fail-under=100 --expand-coverage-report --format json:quality/diff-cover-crosscheck.json

lint:
	$(PYTHON) -m ruff check src tests scripts

format-check:
	$(PYTHON) -m ruff format --check src tests scripts

type:
	$(PYTHON) -m mypy src

security:
	$(PYTHON) -m bandit -q -r src/xrp_regime_engine

verify:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/verify_repository.py

manifest:
	$(PYTHON) scripts/build_manifest.py

manifest-check:
	$(PYTHON) scripts/build_manifest.py --check

quality-evidence:
	$(PYTHON) scripts/quality_evidence.py --coverage quality/coverage_policy.json

check-fast: compile lint format-check type security coverage-policy changed-coverage verify manifest-check quality-evidence

flake-gate:
	$(PYTHON) scripts/run_flake_gate.py --runs 3 --output quality/flake_gate.json

mutation:
	rm -rf mutants .mutmut-cache
	mkdir -p quality
	-mutmut run
	mutmut junitxml --suspicious-policy=failure --untested-policy=failure > quality/mutmut.xml
	$(PYTHON) scripts/check_mutation_score.py quality/mutmut.xml --threshold 90 --report quality/mutation_policy.json

api:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m xrp_regime_engine.cli api

wheel:
	rm -rf dist build
	$(PYTHON) -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .

reproducible-wheel:
	rm -rf dist-a dist-b build
	SOURCE_DATE_EPOCH=1704067200 $(PYTHON) -m pip wheel --no-deps --no-build-isolation --wheel-dir dist-a .
	rm -rf build
	SOURCE_DATE_EPOCH=1704067200 $(PYTHON) -m pip wheel --no-deps --no-build-isolation --wheel-dir dist-b .
	mkdir -p quality
	test "$$(sha256sum dist-a/*.whl | awk '{print $$1}')" = "$$(sha256sum dist-b/*.whl | awk '{print $$1}')"
	sha256sum dist-a/*.whl | tee quality/wheel.sha256

wheel-smoke: reproducible-wheel
	rm -rf /tmp/xrp-wheel-smoke
	$(PYTHON) -m venv /tmp/xrp-wheel-smoke
	/tmp/xrp-wheel-smoke/bin/python -m pip install dist-a/*.whl
	/tmp/xrp-wheel-smoke/bin/python -c 'import xrp_regime_engine; print(xrp_regime_engine.__version__)'
	/tmp/xrp-wheel-smoke/bin/xrp-regime --help >/dev/null

sbom:
	mkdir -p quality
	cyclonedx-py environment --output-format JSON --output-reproducible --output-file quality/sbom.json

audit:
	mkdir -p quality
	pip-audit --format json --output quality/pip-audit.json

clean:
	rm -rf state/demo .pytest_cache .mypy_cache .ruff_cache .hypothesis mutants .mutmut-cache htmlcov build dist dist-a dist-b quality coverage.json coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f \( -name '*.pyc' -o -name '.coverage' \) -delete
