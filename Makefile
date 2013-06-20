clean:
	find . -name '*.pyc' -delete
	rm -f .coverage

test:
	@echo Testing...
	@nosetests --nologcapture

coverage:
	@echo Testing with coverage...
	@nosetests --nologcapture --with-coverage --cover-package=juju_tests

lint:
	@echo  Validating Python syntax...
	@echo "`find -name "*.py" -exec pep8 {} \;`"
	@echo `grep -rl '^#!/.*python' .` | xargs -r -n1 pep8 && echo OK

check: test lint

all: clean coverage lint
