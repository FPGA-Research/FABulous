{% if obj.display %}
   {% if is_own_page %}
{{ obj.id }}
{{ "=" * obj.id | length }}

   {% endif %}
.. py:{% if obj.is_type_alias() %}type{% else %}{{ obj.type }}{% endif %}:: {% if is_own_page %}{{ obj.id }}{% else %}{{ obj.name }}{% endif %}
   {% if obj.is_type_alias() %}
      {% if obj.value %}

   :canonical: {{ obj.value|format_option_type_for_rst }}
      {% endif %}
   {% else %}
      {% if obj.annotation is not none %}

   :type: {% if obj.annotation %} {{ obj.annotation|format_option_type_for_rst }}{% endif %}
      {% endif %}
      {% if obj.value is not none %}

         {% if obj.value.splitlines()|count > 1 %}
   :value: Multiline-String

   .. raw:: html

      <details><summary>Show Value</summary>

   .. code-block:: python

      {{ obj.value|indent(width=6,blank=true) }}

   .. raw:: html

      </details>

         {% else %}
   :value: {{ obj.value|truncate(100) }}
         {% endif %}
      {% endif %}
   {% endif %}

   {% if obj.docstring %}

   .. autoapi-nested-parse::

      {{ obj.docstring|normalize_docstring_for_rst|indent(6) }}
   {% endif %}
{% endif %}
