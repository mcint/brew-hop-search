.PHONY: test build readme tag release release-rc release-yes clean help

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

release-yes: ## Unattended release (prompts pre-answered)
	./scripts/release.sh --yes --release

dry-run: ## Dry-run release (show plan without executing)
	./scripts/release.sh --dry-run

bump: ## Bump patch version
	./scripts/bump-version.sh

clean: ## Remove build artifacts
	rm -rf dist/ build/ *.egg-info src/*.egg-info

version: ## Show current version
	@echo $(VERSION)
