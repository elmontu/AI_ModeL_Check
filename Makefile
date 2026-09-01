PYTHON ?= python3

.PHONY: help compile test schemas links formal check verify build clean

help:
	@echo "compile  Compile Python sources and tests"
	@echo "test     Run the complete Python test suite"
	@echo "schemas  Replay current JSON Schemas and their byte manifest"
	@echo "links    Check local links in repository Markdown files"
	@echo "formal   Verify the Lean build and theorem boundary"
	@echo "check    Run compile, test, schema, and Markdown-link checks"
	@echo "verify   Run check plus formal verification"
	@echo "build    Build Python distribution artifacts"
	@echo "clean    Remove local build and Python cache artifacts (keeps output/)"

compile:
	$(PYTHON) -m compileall -q src tests scripts

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

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
	$(PYTHON) -c "import shutil; from pathlib import Path; [path.unlink() for path in Path('.').rglob('*.py[co]')]; [shutil.rmtree(path) for path in Path('.').rglob('__pycache__') if path.is_dir()]; [shutil.rmtree(path, ignore_errors=True) for path in (Path('build'), Path('dist'), Path('src/model_release_assurance.egg-info'))]"
