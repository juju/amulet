PY := venv/bin/python
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

# ###########
# Build
# ###########

.PHONY: install
install: venv develop

venv: $(PY)
$(PY):
	python3 -m venv venv
	curl https://bootstrap.pypa.io/ez_setup.py | $(PY)
	venv/bin/easy_install pip || venv/local/bin/easy_install pip
	rm setuptools*.zip

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
	sudo apt-get $(shell tty -s || echo -y) install python3-dev juju-core bzr

# ###########
# Develop
# ###########

$(NOSE): $(PY)
	$(PIP) install -r test-requires.txt

.PHONY: test
test: $(NOSE)
	make py3test

# This is a private target used to get around finding nose in different paths.
# Do not call this manually, just use make test.
.PHONY: py3test
py3test:
	@echo Testing Python 3...
	@$(NOSE) --nologcapture

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
