PYTHON := .venv/bin/python
RUFF := .venv/bin/ruff
.PHONY: setup discover-recipes extend-recipes plan-recipes collect-recipes resume collect-foodlion normalize deduplicate match publish build pipeline validate test format lint check serve
setup:
	uv venv --python python3.12 --allow-existing .venv
	uv pip install --python $(PYTHON) -r requirements-dev.txt
discover-recipes extend-recipes plan-recipes collect-recipes collect-foodlion normalize deduplicate match publish build pipeline validate:
	$(PYTHON) -m recipe_system.cli $@
resume: collect-recipes
format:
	$(RUFF) format recipe_system tests scripts
lint:
	$(RUFF) check recipe_system tests scripts
	node --check site/app.js
test:
	$(PYTHON) -m pytest -q
check: format lint test pipeline
serve:
	$(PYTHON) -m http.server 8000 --bind 127.0.0.1 --directory site/dist
