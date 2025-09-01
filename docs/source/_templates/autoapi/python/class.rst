{# Enhanced standalone class template with hierarchical organization #}
{{ obj.name }}
{{ "^" * (obj.name|length) }}

.. py:class:: {{ obj.name }}{% if obj.args %}({{ obj.args }}){% endif %}
   :module: {{ obj.module }}

   {% if obj.bases %}
   {% set bases = obj.bases | map(attribute='name') | list %}
   {% if bases %}

   **Inheritance:** {{ bases | join(' → ') }} → {{ obj.name }}
   {% endif %}
   {% endif %}

   {% if obj.docstring %}
   {{ obj.docstring }}
   {% endif %}

   {% set attributes = obj.children | selectattr('type', 'equalto', 'data') | list %}
   {% set properties = obj.children | selectattr('type', 'equalto', 'property') | list %}
   {% set methods = obj.children | selectattr('type', 'equalto', 'method') | list %}

   {% if attributes %}

   Attributes
   ~~~~~~~~~~

   {% for attr in attributes if attr.display %}
   .. py:attribute:: {{ attr.name }}
      :module: {{ obj.module }}

      {% if attr.docstring %}{{ attr.docstring }}{% endif %}

   {% endfor %}
   {% endif %}

   {% if properties %}

   Properties
   ~~~~~~~~~~

   {% for prop in properties if prop.display %}
   .. py:property:: {{ prop.name }}
      :module: {{ obj.module }}

      {% if prop.docstring %}{{ prop.docstring }}{% endif %}

   {% endfor %}
   {% endif %}

   {% if methods %}

   Methods
   ~~~~~~~

   {% for method in methods if method.display %}
   .. py:method:: {{ method.name }}{% if method.args %}{{ method.args }}{% endif %}
      :module: {{ obj.module }}

      {% if method.docstring %}{{ method.docstring }}{% endif %}

   {% endfor %}
   {% endif %}
