PY := venv/bin/python
PIP := venv/bin/pip
NOSE := venv/bin/nosetests-3.3

# ###########
# Build
# ###########

.PHONY: install
install: venv develop

venv: $(PY)
$(PY):
	python3 -m venv venv
	curl https://bitbucket.org/pypa/setuptools/raw/bootstrap/ez_setup.py | $(PY)
	curl https://raw.github.com/pypa/pip/master/contrib/get-pip.py | $(PY)
	rm setuptools*.tar.gz

.PHONY: clean_all
clean_all: clean clean_venv

.PHONY: clean_venv
clean_venv:
	rm -rf venv

.PHONY: clean
clean:
	find . -name '*.pyc' -delete
	find . -name '*.bak' -delete
	rm -f .coverage

develop: lib/python*/site-packages/aumlet.egg-link
lib/python*/site-packages/aumlet.egg-link:
	$(PY) setup.py develop

.PHONY: sysdeps
sysdeps:
	sudo apt-get install python3-dev

# ###########
# Develop
# ###########

$(NOSE):
	$(PIP) install -r test-requires.txt

.PHONY: test
test: $(NOSE)
	@echo Testing Python 3...
	@$(NOSE) --nologcapture

.PHONY: coverage
coverage:
	@echo Testing with coverage...
	@$(NOSE) --nologcapture --with-coverage --cover-package=juju_tests

.PHONY: lint
lint:
	@find $(sources) -type f \( -iname '*.py' ! -iname '__init__.py' \) -print0 | xargs -r0 flake8

.PHONY: check
check: test lint

.PHONY: all
all: clean venv coverage lint


# ###########
# Deploy
# ###########
.PHONY: dist
dist:
	$(PY) setup.py sdist

.PHONY: upload
upload:
	$(PY) setup.py sdist upload

.PHONY: version_update
version_update:
	$(EDITOR) setup.py
