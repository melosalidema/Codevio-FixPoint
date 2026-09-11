.PHONY: test eval run lint typecheck

test:
	python -m pytest -q

eval:
	python -m evals.runner

run:
	uvicorn api.main:app --reload

lint:
	ruff check .

typecheck:
	mypy core worker adapters
