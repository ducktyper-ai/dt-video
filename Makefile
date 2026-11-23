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
	@d="$$(git rev-parse --git-path hooks)"; mkdir -p "$$d"; \
	if [ -e "$$d/pre-push" ] && ! grep -q "make verify" "$$d/pre-push"; then \
	  echo "existing pre-push hook kept; add 'make verify' to it by hand" >&2; exit 1; fi; \
	printf '#!/bin/sh\nexec make verify\n' > "$$d/pre-push"; chmod +x "$$d/pre-push"; \
	echo "pre-push -> make verify ($$d)"

doctor:
	$(UV) run dt-video doctor

# Release archive of the exact commit. No build step: pure Python, installed with uv from the archive.
# Output: dist/dt-video-<version>-darwin-arm64.tar.gz and .sha256. The tag v<version> must be on MAIN_REF; the archive is made from the tagged commit.
VERSION := $(shell sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -1)
ARCHIVE := dist/dt-video-$(VERSION)-darwin-arm64.tar.gz

# MAIN_REF is the canonical main; fetch it first (git fetch upstream main). Override on hosts with another remote name.
MAIN_REF ?= upstream/main

release:
	@set -e; tag="v$(VERSION)"; \
	git rev-parse -q --verify "refs/tags/$$tag" >/dev/null || { echo "tag $$tag does not exist" >&2; exit 1; }; \
	commit=$$(git rev-list -n1 "$$tag"); \
	git merge-base --is-ancestor "$$commit" "$(MAIN_REF)" || { echo "$$tag ($$commit) is not on $(MAIN_REF)" >&2; exit 1; }; \
	tagged=$$(git show "$$commit:pyproject.toml" | sed -n 's/^version = "\(.*\)"/\1/p' | head -1); \
	test "$$tagged" = "$(VERSION)" || { echo "tagged pyproject version $$tagged != $(VERSION)" >&2; exit 1; }; \
	git show "$$commit:CHANGELOG.md" | grep -q "^## \[$(VERSION)\]" || { echo "tagged CHANGELOG has no $(VERSION) entry" >&2; exit 1; }; \
	test ! -e $(ARCHIVE) || { echo "$(ARCHIVE) exists; refusing to overwrite a release" >&2; exit 1; }; \
	mkdir -p dist; \
	git archive --format=tar.gz --prefix=dt-video-$(VERSION)/ -o $(ARCHIVE) "$$commit"; \
	(cd dist && shasum -a 256 $(notdir $(ARCHIVE)) > $(notdir $(ARCHIVE)).sha256); \
	echo "archived $$tag = $$commit"; cat $(ARCHIVE).sha256

clean:
	rm -rf build dist .coverage htmlcov .mypy_cache .pytest_cache .ruff_cache
	find . -type d -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} +
