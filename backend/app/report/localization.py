"""Bundled message resources for the two existing fixed report templates."""
from html import escape
from backend.app.presentation.locale import current_locale
from backend.app.presentation.messages import catalog


def report_template_resources():
    return {'ui_locale':current_locale().value, **{
        'ui_'+key.replace('.','_'):escape(value,quote=True)
        for key,value in catalog(current_locale().value).items() if '{' not in value
    }}
