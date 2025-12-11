check: lint test

install:
	uv sync

test:
	uv run pytest tests -vv

doc:
	cd docs && make html

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache
	find . -name '*.pyc' -type f -exec rm -rf {} +
	find . -name '__pycache__' -exec rm -rf {} +

build: clean
	uv build

publish: build
	uv publish

lint-ruff:
	uv run ruff check .
	uv run ruff format --check .

lint-mypy:
	uv run mypy flask_pydantic_spec

lint: lint-mypy lint-ruff

format:
	uv run ruff format .
	uv run ruff check --fix .

.PHONY: test doc
