default: lint test

[group("utils")]
install:
    uv sync

[group("utils")]
docs:
    uv sync --group=docs && cd docs && uv run make html

[group("utils")]
clean:
    rm -rf docs/_build dist
    find . -type d -name "__pycache__" -exec rm -rf {} +
    find . -type d -name "*.pyc" -exec rm -f {} +

[group("utils")]
build: clean
    uv build

[group("utils")]
publish: build
    uv publish

[group("test")]
test:
    uv run pytest tests -vv

[group("lint")]
lint-ruff:
    uv run ruff check .
    uv run ruff format --check .

[group("lint")]
lint-mypy:
    uv run mypy flask_pydantic_spec

[group("lint")]
lint: lint-ruff lint-mypy

[group("format")]
format:
    uv run ruff format .
    uv run ruff check --fix .
