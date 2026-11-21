PYTHON_VERSION := 3.12
UV := uv
SRC := src tests

.PHONY: help env sync format lint typecheck test verify clean doctor hooks

help:
	@echo "dt-video"
	@echo "  make sync      Install the package with dev extras via uv"
	@echo "  make format    Format with ruff"
	@echo "  make lint      Ruff lint"
	@echo "  make typecheck mypy"
	@echo "  make test      pytest"
	@echo "  make verify    lint + typecheck + test"
	@echo "  make doctor    dt-video doctor"
	@echo "  make hooks     install a git pre-push hook that runs make verify"

env:
	$(UV) venv --python $(PYTHON_VERSION)

sync:
	$(UV) sync --extra dev

format:
	$(UV) run ruff format $(SRC)

lint:
	$(UV) run ruff check $(SRC)
	$(UV) run ruff format --check $(SRC)

typecheck:
	$(UV) run mypy

test:
	$(UV) run pytest tests

verify: lint typecheck test

hooks:
	@mkdir -p .git/hooks
	@printf '#!/bin/sh\nexec make verify\n' > .git/hooks/pre-push
	@chmod +x .git/hooks/pre-push
	@echo "Installed .git/hooks/pre-push -> make verify"

doctor:
	$(UV) run dt-video doctor

clean:
	rm -rf build dist .coverage htmlcov .mypy_cache .pytest_cache .ruff_cache
	find . -type d -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} +
