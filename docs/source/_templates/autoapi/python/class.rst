{# Enhanced standalone class template with hierarchical organization #}
{{ obj.name }}
{{ "^" * (obj.name|length) }}

.. py:class:: {{ obj.name }}{{ "(" + obj.args + ")" if obj.args else "" }}

   {% if obj.bases %}
   {% set inheritance = obj.bases|format_inheritance_for_rst(obj.name) %}
   {% if inheritance %}

   {{ inheritance }}
   {% endif %}
   {% endif %}

   {% if obj.docstring %}

   .. autoapi-nested-parse::

      {{ obj.docstring|normalize_docstring_for_rst|indent(6) }}
   {% endif %}

   {% set attributes = obj.children | selectattr('type', 'equalto', 'data') | selectattr('display') | list %}
   {% set properties = obj.children | selectattr('type', 'equalto', 'property') | selectattr('display') | list %}
   {% set methods = obj.children | selectattr('type', 'equalto', 'method') | selectattr('display') | list %}

   {% if attributes %}

   Attributes
   ~~~~~~~~~~

   {% for attr in attributes %}

   {{ attr.render()|indent(3) }}
   {% endfor %}
   {% endif %}

   {% if properties %}

   Properties
   ~~~~~~~~~~

   {% for prop in properties %}

   {{ prop.render()|indent(3) }}
   {% endfor %}
   {% endif %}

   {% if methods %}

   Methods
   ~~~~~~~

   {% for method in methods %}

   {{ method.render()|indent(3) }}
   {% endfor %}
   {% endif %}
