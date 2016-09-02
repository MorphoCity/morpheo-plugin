.PHONY: doc dist

BUILDDIR=../build
BUILDDOC=${BUILDDIR}/doc

all: doc

clean:
	rm -rf $(BUILDDOC)

doc: apidoc html

html:
	mkdir -p ${BUILDDOC}/html
	sphinx-build -b html .  ${BUILDDOC}/html

apidoc:
	sphinx-apidoc  -o . ../src/morpheo/core

# Build pdf doc
# You need to have a latex distribution installed.
# See README_DOC for requirements
pdf:
	mkdir -p ${BUILDDOC}/latex
	sphinx-build -b latex . ${BUILDDOC}/latex
	cd ${BUILDDOC}/latex && pdflatex src.tex

