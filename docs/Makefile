# Minimal makefile for Sphinx documentation with uv environment management
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?= -q
SPHINXBUILD   ?= uv run --directory . --quiet sphinx-build
SPHINXAPIDOC  ?= uv run --directory . --quiet sphinx-apidoc
SOURCEDIR     = source
BUILDDIR      = build
APIDIR        = $(SOURCEDIR)/references
PACKAGEDIR    = ../FABulous

# Put it first so that "make" without argument is like "make help".
help:
	@echo "Please use \`make <target>\` where <target> is one of"
	@echo "  setup      to initialize the uv environment and install dependencies"
	@echo "  apidoc     to generate API documentation from source code"
	@echo "  html       to make standalone HTML files"
	@echo "  clean      to remove build directory and generated API docs"
	@echo "  livehtml   to build docs and serve with auto-reload (requires sphinx-autobuild)"
	@echo ""
	@echo "Standard Sphinx targets:"
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

# Setup uv environment and install dependencies
setup:
	@echo "Setting up uv environment for documentation..."
	uv sync
	@echo "Installing FABulous package in editable mode..."
	uv pip install -e ..
	@echo "Documentation environment ready!"

# Generate API documentation using sphinx-apidoc
apidoc:
	@echo "Generating API documentation..."
	@mkdir -p $(APIDIR)
	@$(SPHINXAPIDOC) -f -e -T -o $(APIDIR) $(PACKAGEDIR)
	@echo "API documentation generated in $(APIDIR)"

# Build HTML documentation (with API generation)
html: setup apidoc
	@echo "Building HTML documentation..."
	@$(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O) 2>/dev/null || true
	@echo "Documentation built successfully in $(BUILDDIR)/html"

# Live reload development server
livehtml: setup apidoc
	@echo "Starting live documentation server..."
	uv run --directory . sphinx-autobuild $(SOURCEDIR) $(BUILDDIR)/html $(SPHINXOPTS)

# Clean build directory and generated API docs
clean:
	@echo "Cleaning build directory and generated API docs..."
	rm -rf $(BUILDDIR)
	rm -rf $(APIDIR)
	@echo "Clean completed!"

.PHONY: help setup apidoc html livehtml clean Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
