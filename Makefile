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

lint-flake8:
	# stop the build if there are Python syntax errors or undefined names
	uv run flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	# exit-zero treats all errors as warnings
	uv run flake8 . --count --exit-zero --statistics

lint-mypy:
	uv run mypy flask_pydantic_spec

lint-black:
	uv run black --check tests flask_pydantic_spec

lint: lint-mypy lint-black lint-flake8

format:
	uv run black tests flask_pydantic_spec

.PHONY: test doc
