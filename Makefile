# pg_gnufind/Makefile
srcdir     = .
EXTENSION  = gnufind			# the extensions name
EXTVERSION = $(shell grep default_version $(srcdir)/$(EXTENSION).control | sed -e "s/default_version[[:space:]]*=[[:space:]]*'\([^']*\)'/\1/")
DATA       = gnufind--1.0.0.sql # script files to install
# REGRESS   = geekspeak_test		# unit and regression tests

# postgres build stuff
PG_CONFIG = pg_config
PGXS := $(shell $(PG_CONFIG) --pgxs)
include $(PGXS)

install: python_code

python_code: setup.py
	cp $(srcdir)/setup.py ./setup--$(EXTVERSION).py
	sed -i -e "s/__VERSION__/$(EXTVERSION)-dev/g" ./setup--$(EXTVERSION).py
	$(PYTHON) ./setup--$(EXTVERSION).py install
	rm ./setup--$(EXTVERSION).py
