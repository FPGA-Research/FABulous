{{ obj.name }}
{{ '=' * (obj.name|length) }}

{% if obj.docstring %}
{{ obj.docstring }}
{% endif %}

.. toctree::
   :maxdepth: 2
   :titlesonly:

{% for p in obj.subpackages if p.display %}
   {{ p.docname }}
{% endfor %}
{% for m in obj.submodules if m.display %}
   {{ m.docname }}
{% endfor %}
{% for c in obj.children if c.display and c.objtype in ['package','module'] %}
   {{ c.docname }}
{% endfor %}
