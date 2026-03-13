{% if obj.display %}
   {% if is_own_page %}
{{ obj.id }}
{{ "=" * obj.id | length }}

   {% endif %}
.. py:property:: {% if is_own_page %}{{ obj.id}}{% else %}{{ obj.short_name }}{% endif %}
   {% if obj.annotation %}

   :type: {{ obj.annotation|format_option_type_for_rst }}
   {% endif %}
   {% for property in obj.properties %}

   :{{ property }}:
   {% endfor %}

   {% if obj.docstring %}

   .. autoapi-nested-parse::

      {{ obj.docstring|normalize_property_docstring_for_rst|indent(6) }}
   {% endif %}
{% endif %}
