# Minimal makefile for Sphinx documentation with uv environment management
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?= -q -n
SPHINXBUILD   ?= uv run --directory . --quiet sphinx-build
SOURCEDIR     = source
BUILDDIR      = build
PACKAGEDIR    = ../FABulous
PORT          ?= 8000

# Put it first so that "make" without argument is like "make help".
help:
	@echo "Please use \`make <target>\` where <target> is one of"
	@echo "  setup      to initialize the uv environment and install dependencies"
	@echo "  html       to make standalone HTML files"
	@echo "  serve      to serve built docs on localhost:$(PORT) and open browser"
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

# Build HTML documentation
html: setup
	@echo "Building final HTML documentation..."
	@$(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
	@echo "Documentation built successfully in $(BUILDDIR)/html"

# Serve built documentation with Python HTTP server and open browser
serve:
	@if [ ! -d "$(BUILDDIR)/html" ]; then \
		echo "Error: $(BUILDDIR)/html not found. Run 'make html' first."; \
		exit 1; \
	fi
	@echo "Starting web server on http://localhost:$(PORT)"
	@echo "Opening browser..."
	@(sleep 1 && xdg-open http://localhost:$(PORT) 2>/dev/null || \
	  open http://localhost:$(PORT) 2>/dev/null || \
	  start http://localhost:$(PORT) 2>/dev/null || \
	  echo "Please open http://localhost:$(PORT) in your browser") &
	@cd $(BUILDDIR)/html && python3 -m http.server $(PORT)

# Live reload development server
livehtml: setup
	@echo "Starting live documentation server..."
	uv run --directory . sphinx-autobuild $(SOURCEDIR) $(BUILDDIR)/html $(SPHINXOPTS)

# Clean build directory and generated API docs
clean:
	@echo "Cleaning build directory and generated API docs..."
	rm -rf $(BUILDDIR)
	rm -rf $(SOURCEDIR)/generated_doc
	@echo "Clean completed!"

# Force regeneration of AutoAPI docs (useful for development)
clean-autoapi:
	@echo "Cleaning AutoAPI generated files..."
	rm -rf $(SOURCEDIR)/generated_doc
	@echo "AutoAPI clean completed!"

.PHONY: help setup apidoc html serve livehtml clean clean-autoapi Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
