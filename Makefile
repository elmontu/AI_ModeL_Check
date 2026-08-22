PYTHON ?= python3
SCHEMA_TMP ?= /tmp/model-release-assurance-schemas

.PHONY: help compile test schemas check build clean

help:
	@echo "Targets: compile, test, schemas, check, build, clean"

compile:
	$(PYTHON) -m compileall -q src tests scripts

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

schemas:
	mkdir -p $(SCHEMA_TMP)
	PYTHONPATH=src $(PYTHON) -m model_release_assurance schema --output $(SCHEMA_TMP)/assessment-request-v3.json
	diff -u schemas/assessment-request-v3.json $(SCHEMA_TMP)/assessment-request-v3.json
	PYTHONPATH=src $(PYTHON) -m model_release_assurance schema --kind policy --output $(SCHEMA_TMP)/policy-bundle-v1.json
	diff -u schemas/policy-bundle-v1.json $(SCHEMA_TMP)/policy-bundle-v1.json
	PYTHONPATH=src $(PYTHON) -m model_release_assurance schema --kind report --output $(SCHEMA_TMP)/assessment-report-v3.json
	diff -u schemas/assessment-report-v3.json $(SCHEMA_TMP)/assessment-report-v3.json
	PYTHONPATH=src $(PYTHON) -m model_release_assurance schema --kind optimization --output $(SCHEMA_TMP)/optimization-request-v2.json
	diff -u schemas/optimization-request-v2.json $(SCHEMA_TMP)/optimization-request-v2.json
	PYTHONPATH=src $(PYTHON) -m model_release_assurance schema --kind optimization-report --output $(SCHEMA_TMP)/optimization-report-v2.json
	diff -u schemas/optimization-report-v2.json $(SCHEMA_TMP)/optimization-report-v2.json
	PYTHONPATH=src $(PYTHON) -m model_release_assurance schema --kind optimization-manifest --output $(SCHEMA_TMP)/signed-optimization-manifest-v2.json
	diff -u schemas/signed-optimization-manifest-v2.json $(SCHEMA_TMP)/signed-optimization-manifest-v2.json
	PYTHONPATH=src $(PYTHON) -m model_release_assurance schema --kind manifest --output $(SCHEMA_TMP)/signed-manifest-v1.json
	diff -u schemas/signed-manifest-v1.json $(SCHEMA_TMP)/signed-manifest-v1.json

check: compile test schemas

build:
	$(PYTHON) -m build

clean:
	$(PYTHON) -c "from pathlib import Path; [path.unlink() for path in Path('.').rglob('*.py[co]')]"
