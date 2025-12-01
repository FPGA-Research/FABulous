API Reference
=============

This section contains the complete software documentation for FABulous.

The API is organized hierarchically - click on a package to see its submodules and classes.

.. toctree::
   :titlesonly:

   {% for page in pages|selectattr("is_top_level_object") %}
   {{ page.include_path }}
   {% endfor %}
