# pg_gnufind/Makefile

EXTENSION = gnufind       # the extensions name
DATA = gnufind--1.0.0.sql # script files to install
# REGRESS = geekspeak_test    # unit and regression tests

# postgres build stuff
PG_CONFIG = pg_config
PGXS := $(shell $(PG_CONFIG) --pgxs)
include $(PGXS)
