PY := venv/bin/python
PY2 := venvpy2/bin/python
# If the bin version does not exist look in venv/local/bin
ifeq ($(wildcard venv/bin/pip),)
  PIP = venv/local/bin/pip
else
  PIP = venv/bin/pip
endif
# If the bin version does not exist look in venv/local/bin
ifeq ($(wildcard venv/bin/nosetests),)
  NOSE = venv/local/bin/nosetests
else
  NOSE = venv/bin/nosetests
endif
# If the bin version does not exist look in venv/local/bin
ifeq ($(wildcard venvpy2/bin/pip),)
  PIP2 = venvpy2/local/bin/pip
else
  PIP2 = venvpy2/bin/pip
endif
# If the bin version does not exist look in venv/local/bin
ifeq ($(wildcard venvpy2/bin/nosetests),)
  NOSE2 = venvpy2/local/bin/nosetests
else
  NOSE2 = venvpy2/bin/nosetests
endif

# ###########
# Build
# ###########

.PHONY: install
install: venv venvpy2 develop

venv: $(PY)
$(PY):
	python3 -m venv venv --without-pip
	curl https://bitbucket.org/pypa/setuptools/raw/bootstrap/ez_setup.py | $(PY)
	venv/bin/easy_install pip
	rm setuptools*.zip

venvpy2: $(PY2)
$(PY2):
	virtualenv venvpy2

.PHONY: clean_all
clean_all: clean clean_venv

.PHONY: clean_venv
clean_venv:
	rm -rf venv
	rm -rf venvpy2

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
	sudo apt-get $(shell tty -s || echo -y) install python3-dev juju-core bzr
	sudo apt-get $(shell tty -s || echo -y) install python-dev python-virtualenv python-pip

# ###########
# Develop
# ###########

$(NOSE): $(PY)
	$(PIP) install -r test-requires.txt

$(NOSE2): $(PY2)
	$(PIP2) install -r test-requires.txt

.PHONY: test
test: $(NOSE) $(NOSE2)
	make py3test
	make py2test

# This is a private target used to get around finding nose in different paths.
# Do not call this manually, just use make test.
.PHONY: py3test
py3test:
	@echo Testing Python 3...
	@$(NOSE) --nologcapture

.PHONY: py2test
py2test:
	@echo Testing Sentry code with Python 2...
	@$(NOSE2) tests/test_sentry.py --nologcapture

.PHONY: coverage
coverage: $(NOSE)
	@echo Testing with coverage...
	@$(NOSE) --nologcapture --with-coverage --cover-package=amulet

.PHONY: lint
lint:
	@find $(sources) -type f \( -iname '*.py' ! -iname '__init__.py' ! -iwholename '*venv/*' \) -print0 | xargs -r0 flake8

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
