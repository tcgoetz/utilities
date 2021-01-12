#
# This Makefile automates running tests for the project.
#

PROJECT_BASE ?= $(CURDIR)/../.

include $(PROJECT_BASE)/defines.mk

PYTHONPATH=${PROJECT_BASE}/..
export PYTHONPATH

DB_TEST_GROUPS=
DB_OBJECTS_TEST_GROUPS=db_object
TEST_GROUPS=$(DB_TEST_GROUPS) $(DB_OBJECTS_TEST_GROUPS)


#
# Over all targets
#
all: $(ALL_TEST_GROUPS)

db: $(DB_TEST_GROUPS)

db_objects: $(DB_OBJECTS_TEST_GROUPS)

verify_commit: db_objects

clean:
	rm -f *.pyc
	rm -f *.log
	rm -f *.txt
	rm -rf __pycache__

#
# Targets for testing smaller slices of functionality.
#
$(TEST_GROUPS):
	echo ${PYTHONPATH}
	$(PYTHON) test_$@.py

test_%:
	$(PYTHON) -m unittest -v $@

.PHONY: all db db_objects clean
