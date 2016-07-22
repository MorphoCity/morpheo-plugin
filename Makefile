.PHONY: doc dist

BUILDDIR=${shell pwd}/build
BUILDDOC=${BUILDDIR}/doc

DIST=${BUILDDIR}/dist


all: dist doc

dist: dirs 
	python setup.py sdist --dist-dir=${DIST}


clean:
	rm -rf $(BUILDDIR)

test:
	cd tests && py.test -v

# Documentation

doc: apidoc html

html: dirs 
	mkdir -p ${BUILDDOC}/html
	sphinx-build -b html doc/  ${BUILDDOC}/html

apidoc:
	sphinx-apidoc  -o doc ./src/morpheo/core

# Build pdf doc
# You need to have a latex distribution installed.
# See README_DOC for requirements
pdf: dirs
	mkdir -p ${BUILDDOC}/latex
	sphinx-build -b latex doc/  ${BUILDDOC}/latex
	cd ${BUILDDOC}/latex && pdflatex src.tex

dirs:
	mkdir -p ${DIST}

