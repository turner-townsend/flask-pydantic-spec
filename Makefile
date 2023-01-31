check: style test

install:
	pip install -e .

test:
	pytest tests -vv

doc:
	cd docs && make html

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache
	find . -name '*.pyc' -type f -exec rm -rf {} +
	find . -name '__pycache__' -exec rm -rf {} +

build: clean
	python setup.py sdist bdist_wheel

publish: build
	twine upload dist/*

style:
	# stop the build if there are Python syntax errors or undefined names
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	# exit-zero treats all errors as warnings
	flake8 . --count --exit-zero --statistics

lint:
	mypy flask_pydantic_openapi

format:
	black tests flask_pydantic_openapi

.PHONY: test doc
