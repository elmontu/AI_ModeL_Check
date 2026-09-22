PYTHON ?= python3
COMPILE_CACHE ?= .mra-compile-cache
DEMO_DATASET_PROFILE ?= openml-sick

.PHONY: help demo demo-reference export-poc test-export-poc compile test schemas links formal check verify build clean

help:
	@echo "export-poc      Start the loopback DP export lab on public synthetic data"
	@echo "test-export-poc Check the fixed DP protocol, history, CLI, API and tools"
	@echo "demo            Train XGBoost and run the training-to-assessment demo (experiment dependencies; OpenML by default)"
	@echo "demo-reference  Run the secondary core-only fixture and workflow rehearsal"
	@echo "compile  Compile Python sources and tests"
	@echo "test     Run the complete Python test suite"
	@echo "schemas  Replay current JSON Schemas and their byte manifest"
	@echo "links    Check local links in repository Markdown files"
	@echo "formal   Verify the Lean build and theorem boundary"
	@echo "check    Run compile, test, schema, and Markdown-link checks"
	@echo "verify   Run check plus formal verification"
	@echo "build    Build Python distribution artifacts"
	@echo "clean    Remove local build and Python cache artifacts (keeps output/)"

demo:
	PYTHONPATH=src $(PYTHON) scripts/run_training_release_demo.py --dataset-profile $(DEMO_DATASET_PROFILE)

demo-reference:
	PYTHONPATH=src $(PYTHON) scripts/run_government_health_demo.py

export-poc:
	PYTHONPATH=src $(PYTHON) -m model_release_assurance.export_poc serve

test-export-poc:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -p 'test_export_poc*.py' -v

compile:
	PYTHONPYCACHEPREFIX=$(COMPILE_CACHE) $(PYTHON) -m compileall -q src tests scripts academic/scripts academic/tests

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v
	PYTHONPATH=src $(PYTHON) -m unittest discover -s academic/tests -v

schemas:
	PYTHONPATH=src $(PYTHON) scripts/generate_schema_manifest.py --check

formal:
	$(PYTHON) scripts/verify_formal_protocol.py

links:
	$(PYTHON) scripts/check_markdown_links.py

check: compile test schemas links

verify: check formal

build:
	$(PYTHON) -m build

clean:
	$(PYTHON) -c "import shutil; from pathlib import Path; [path.unlink() for path in Path('.').rglob('*.py[co]')]; [shutil.rmtree(path) for path in Path('.').rglob('__pycache__') if path.is_dir()]; [shutil.rmtree(path, ignore_errors=True) for path in (Path('.pytest_cache'), Path('.mypy_cache'), Path('.ruff_cache'), Path('.mra-compile-cache'), Path('build'), Path('dist'), Path('src/model_release_assurance.egg-info'))]"
