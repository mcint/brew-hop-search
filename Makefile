.PHONY: test build readme tag release release-rc release-test release-yes clean help versions publish publish-test bump bump-dev bump-release

VERSION := $(shell sed -n 's/^__version__ = "\([^"]*\)"/\1/p' src/brew_hop_search/__init__.py)

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-16s %s\n", $$1, $$2}'

test: ## Run tests
	uv run python -m pytest tests/ -x -q --tb=short

build: test ## Build package (runs tests first)
	uv build

readme: ## Regenerate README.md from live output
	./scripts/build-readme.sh > README.md

tag: ## Create rc tag
	./scripts/build-tag.sh

tag-release: ## Create release tag
	./scripts/build-tag.sh --promote

tag-list: ## List version tags
	./scripts/build-tag.sh --list

release: ## Interactive release (test → build → tag → ff main)
	./scripts/release.sh

release-rc: ## Unattended rc release
	./scripts/release.sh --yes --rc

release-test: ## Full release flow → TestPyPI (no main ff, no post-bump)
	./scripts/release.sh --testpypi --release

release-yes: ## Unattended PyPI release (prompts pre-answered)
	./scripts/release.sh --yes --release

dry-run: ## Dry-run release (show plan without executing)
	./scripts/release.sh --dry-run

bump: ## Bump patch version (0.3.1 → 0.3.2)
	./scripts/bump-version.sh

bump-dev: ## Bump + tag .dev0 (0.3.1 → 0.3.2.dev0; no-op if already dev)
	./scripts/bump-version.sh --dev

bump-release: ## Strip .devN (0.3.2.dev0 → 0.3.2; no-op if no dev)
	./scripts/bump-version.sh --release

clean: ## Remove build artifacts
	rm -rf dist/ build/ *.egg-info src/*.egg-info

version: ## Show current version
	@echo $(VERSION)

versions: ## List versions published on PyPI + TestPyPI
	@. scripts/_guards.sh; \
	 echo "# pypi"; pypi_versions pypi; \
	 echo "# testpypi"; pypi_versions testpypi

publish-test: ## Build + publish current version to TestPyPI (with guards)
	./scripts/publish.sh

publish: ## Build + publish current version to PyPI (with guards)
	./scripts/publish.sh --release
