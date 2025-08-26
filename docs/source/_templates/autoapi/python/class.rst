{# Custom AutoAPI class template to group attributes and methods (standalone) #}
.. py:class:: {{ obj.name }}{% if obj.args %}({{ obj.args }}){% endif %}

   {% if obj.bases %}
   {% set bases = obj.bases | map(attribute='name') | list %}
   {% if bases %}
   Bases: {{ bases | join(', ') }}
   {% endif %}
   {% endif %}

   {% if obj.docstring %}
   {{ obj.docstring | indent(3) }}
   {% endif %}

   {% set methods = obj.children | selectattr('type', 'equalto', 'method') | list %}
   {% set functions = obj.children | selectattr('type', 'equalto', 'function') | list %}

   {% if methods or functions %}
   Methods
   -------

   {% for m in methods if m.display %}
   .. py:method:: {{ m.name }}{{ m.args }}

      {% if m.docstring %}{{ m.docstring | indent(6) }}{% endif %}
   {% endfor %}

   {% for f in functions if f.display %}
   .. py:function:: {{ f.name }}{{ f.args }}

      {% if f.docstring %}{{ f.docstring | indent(6) }}{% endif %}
   {% endfor %}
   {% endif %}
