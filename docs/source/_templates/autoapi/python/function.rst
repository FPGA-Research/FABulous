{% if obj.display %}
   {% if is_own_page %}
{{ obj.id }}
{{ "=" * obj.id | length }}

   {% endif %}
.. py:function:: {% if is_own_page %}{{ obj.id }}{% else %}{{ obj.short_name }}{% endif %}{% if obj.type_params %}[{{ obj.type_params }}]{% endif %}({{ obj.args }}){% if obj.obj["return_annotation"] is not none %} -> {{ obj.obj["return_annotation"] }}{% endif %}
   {% for (args, return_annotation) in obj.overloads %}

                 {%+ if is_own_page %}{{ obj.id }}{% else %}{{ obj.short_name }}{% endif %}({{ args }}){% if return_annotation is not none %} -> {{ return_annotation }}{% endif %}
   {% endfor %}
   {% for property in obj.properties %}

   :{{ property }}:
   {% endfor %}

   {% if obj.docstring %}

   .. autoapi-nested-parse::

      {{ obj.docstring|normalize_callable_docstring_for_rst|indent(6) }}
   {% endif %}
{% endif %}
