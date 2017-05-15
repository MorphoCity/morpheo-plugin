.PHONY: all dist

BUILDDIR=${shell pwd}/build
DIST=${BUILDDIR}/dist

PLUGINNAME=morpheo

all: dist

dist: dirs 
	python setup.py sdist --dist-dir=${DIST}


clean:
	rm -rf $(BUILDDIR)

test:
	cd tests && py.test -v

dirs:
	mkdir -p ${DIST}

plugin:
	 git archive --prefix=$(PLUGINNAME)/ -o $(PLUGINNAME).zip $(shell python setup.py --version) $(PLUGINNAME)

