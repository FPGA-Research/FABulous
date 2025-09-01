{# Hierarchical AutoAPI module template with proper nesting #}

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
.. py:class:: {{ c.name }}({{ c.args }})
{% if c.bases %}
   {% set bases = c.bases | map(attribute='name') | list %}
   {% if bases %}

   **Bases:** {{ bases | join(', ') }}
   {% endif %}
{% endif %}
{% if c.docstring %}

   {{ c.docstring | indent(3) }}
{% endif %}

   {% set attributes = c.children | selectattr('type', 'equalto', 'data') | list %}
   {% set properties = c.children | selectattr('type', 'equalto', 'property') | list %}
   {% set methods = c.children | selectattr('type', 'equalto', 'method') | list %}
{% if attributes %}

   **Attributes:**
{% for attr in attributes if attr.display %}

   .. py:attribute:: {{ attr.name }}
      :no-index:
{% if attr.docstring %}

      {{ attr.docstring | indent(6) }}
{% endif %}
{% endfor %}
{% endif %}
{% if properties %}

   **Properties:**
{% for prop in properties if prop.display %}

   .. py:property:: {{ prop.name }}
{% if prop.docstring %}

      {{ prop.docstring | indent(6) }}
{% endif %}
{% endfor %}
{% endif %}
{% if methods %}

   **Methods:**
{% for method in methods if method.display %}

   .. py:method:: {{ method.name }}({{ method.args }})
{% if method.docstring %}

      {{ method.docstring | indent(6) }}
{% endif %}
{% endfor %}
{% endif %}

{% endfor %}
{% endif %}

{% if functions %}
Functions
---------

{% for f in functions if f.display %}
.. py:function:: {{ f.name }}({{ f.args }})

   {% if f.docstring %}{{ f.docstring | indent(3) }}{% endif %}

{% endfor %}
{% endif %}

{% if data %}
Module Attributes
-----------------

{% for d in data if d.display %}
.. py:data:: {{ d.name }}
   :no-index:

   {% if d.docstring %}{{ d.docstring | indent(3) }}{% endif %}

{% endfor %}
{% endif %}
