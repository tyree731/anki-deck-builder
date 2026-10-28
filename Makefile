##anki-deck-builder Makefile: usage: make <command>
##
##Commands:

UV    := uv run --quiet
PATHS := packages

##  help:       show this help
help:
	@grep -h '^##' $(MAKEFILE_LIST) | sed -e 's/^##//'

##  test:       run all tests, including the end-to-end pipeline (needs Chrome or Chromium)
test:
	$(UV) pytest

##  test-fast:  run unit tests only (no real deck builds, no browser)
test-fast:
	$(UV) pytest -m "not browser and not integration"

##  lint:       run the ruff checker
lint:
	$(UV) ruff check $(PATHS)

##  format:     run the ruff formatter, rewriting files
format:
	$(UV) ruff format $(PATHS)

##  typecheck:  run pyright
typecheck:
	$(UV) pyright

##  check:      run lint, typecheck and test
check: lint typecheck test

.PHONY: help test test-fast lint format typecheck check
