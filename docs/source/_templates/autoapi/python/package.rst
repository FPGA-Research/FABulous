{{ obj.name }}
{{ '=' * (obj.name|length) }}

{% if obj.docstring %}
{{ obj.docstring }}

{% endif %}

{% set packages = obj.subpackages | selectattr('display') | list %}
{% set modules = obj.submodules | selectattr('display') | list %}
{% set direct_children = obj.children | selectattr('display') | selectattr('objtype', 'in', ['package','module']) | list %}

{% if packages or modules or direct_children %}

Package Contents
----------------

.. toctree::
   :maxdepth: 2
   :titlesonly:
   :caption: Subpackages and Modules

{% for p in packages %}
   {{ p.docname }}
{% endfor %}
{% for m in modules %}
   {{ m.docname }}
{% endfor %}
{% for c in direct_children %}
   {{ c.docname }}
{% endfor %}

{% endif %}
