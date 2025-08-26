{# Standalone AutoAPI module template to avoid duplicate object descriptions #}

{{ obj.name }}
{{ '=' * (obj.name|length) }}

.. py:module:: {{ obj.name }}

{% if obj.docstring %}
.. autoapi-nested-parse::
   {{ obj.docstring | indent(3) }}
{% endif %}

{% set classes = obj.children | selectattr('type', 'equalto', 'class') | list %}
{% set functions = obj.children | selectattr('type', 'equalto', 'function') | list %}
{% set data = obj.children | selectattr('type', 'equalto', 'data') | list %}

{% if classes %}
Classes
-------
{% for c in classes if c.display %}
{{ c.render() }}
{% endfor %}
{% endif %}

{% if functions %}
Functions
---------
{% for f in functions if f.display %}
.. py:function:: {{ f.name }}{% if f.args %}{{ f.args }}{% endif %}

   {% if f.docstring %}{{ f.docstring | indent(3) }}{% endif %}
{% endfor %}
{% endif %}

{% if data %}
Attributes
----------
{% for d in data if d.display %}
.. py:attribute:: {{ d.name }}
   :no-index:

   {% if d.docstring %}{{ d.docstring | indent(3) }}{% endif %}
{% endfor %}
{% endif %}
