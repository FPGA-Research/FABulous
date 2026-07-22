{% if obj.display %}
   {% if is_own_page %}
{{ obj.id }}
{{ "=" * obj.id | length }}

   {% endif %}
.. py:property:: {% if is_own_page %}{{ obj.id}}{% else %}{{ obj.short_name }}{% endif %}
   {% if obj.annotation %}

   :type: {{ obj.annotation }}
   {% endif %}
   {% for property in obj.properties %}

   :{{ property }}:
   {% endfor %}

   {% if obj.docstring %}

   .. myst-docstring::

      {{ obj.docstring|strip_property_return_sections|indent(6) }}
   {% endif %}
{% endif %}
