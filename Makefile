.PHONY: all dist

BUILDDIR=${shell pwd}/build
DIST=${BUILDDIR}/dist

all: dist

dist: dirs 
	python setup.py sdist --dist-dir=${DIST}


clean:
	rm -rf $(BUILDDIR)

test:
	cd tests && py.test -v

dirs:
	mkdir -p ${DIST}

