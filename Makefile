.PHONY: setup run run-adk web help

help:
	@echo "Targets:"
	@echo "  make setup   - uv sync + remind to copy .env"
	@echo "  make run     - one-shot traced run (MESSAGE=...)"
	@echo "  make run-adk - ADK CLI dev loop (cd agent && adk run shopsafe)"
	@echo "  make web     - live pipeline web UI at http://localhost:8000"

setup:
	uv sync
	@test -f .env || echo "Tip: copy .env.example to .env and add keys."

run:
	cd agent && uv run python main.py "$(if $(MESSAGE),$(MESSAGE),What are the safety concerns with retinol in skincare?)"

run-adk:
	cd agent && uv run adk run shopsafe

web:
	uv run python web/server.py
