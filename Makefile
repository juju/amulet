clean:
	find . -name '*.pyc' -delete
	find . -name '*.bak' -delete
	rm -f .coverage

test:
	@echo Testing Python 3...
	@nosetests3 --nologcapture
	@echo Testing Python 2...
	@nosetests --nologcapture

coverage:
	@echo Testing with coverage...
	@nosetests3 --nologcapture --with-coverage --cover-package=juju_tests

lint:
	@find $(sources) -type f \( -iname '*.py' ! -iname '__init__.py' \) -print0 | xargs -r0 flake8

check: test lint

all: clean coverage lint
