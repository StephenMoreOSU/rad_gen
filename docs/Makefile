# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line.
SPHINXOPTS    =
SPHINX_APIGEN = sphinx-apidoc
SPHINXBUILD   = sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

build-api:
	@echo "Building API documentation"
	@$(SPHINX_APIGEN) -o $(SOURCEDIR)/api/out ../src

clean-api:
	@echo "Cleaning API documentation"
	@rm -rf $(SOURCEDIR)/api/out

all: clean clean-api build-api html

.PHONY: help Makefile all

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)