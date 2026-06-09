.PHONY: setup run run-adk help

help:
	@echo "Targets:"
	@echo "  make setup   - uv sync + remind to copy .env"
	@echo "  make run     - one-shot traced run (MESSAGE=...)"
	@echo "  make run-adk - ADK CLI dev loop (cd agent && adk run shopsafe)"

setup:
	uv sync
	@test -f .env || echo "Tip: copy .env.example to .env and add keys."

run:
	cd agent && uv run python main.py "$(if $(MESSAGE),$(MESSAGE),What are the safety concerns with retinol in skincare?)"

run-adk:
	cd agent && uv run adk run shopsafe
