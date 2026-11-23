PYTHON_VERSION := 3.12
UV := uv
SRC := src tests

.PHONY: help env sync format lint typecheck test verify clean doctor hooks release

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
	@echo "  make release   archive of the tagged HEAD + .sha256 (darwin-arm64 naming)"

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

# Release archive of the exact commit. No build step: pure Python, installed with uv from the archive.
# Output: dist/dt-video-<version>-darwin-arm64.tar.gz and .sha256. HEAD must carry tag v<version>.
VERSION := $(shell sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -1)
ARCHIVE := dist/dt-video-$(VERSION)-darwin-arm64.tar.gz

release:
	@test -z "$$(git status --porcelain)" || { echo "tree not clean" >&2; exit 1; }
	@git describe --exact-match --tags HEAD 2>/dev/null | grep -qx "v$(VERSION)" || { echo "HEAD must be tagged v$(VERSION)" >&2; exit 1; }
	@grep -q "^## \[$(VERSION)\]" CHANGELOG.md || { echo "CHANGELOG has no $(VERSION) entry" >&2; exit 1; }
	@mkdir -p dist
	git archive --format=tar.gz --prefix=dt-video-$(VERSION)/ -o $(ARCHIVE) HEAD
	cd dist && shasum -a 256 $(notdir $(ARCHIVE)) > $(notdir $(ARCHIVE)).sha256
	@cat $(ARCHIVE).sha256

clean:
	rm -rf build dist .coverage htmlcov .mypy_cache .pytest_cache .ruff_cache
	find . -type d -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} +
