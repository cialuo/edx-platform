"""
Core logic for Comprehensive Theming.
"""
from django.conf import settings

from .helpers import get_themes


def enable_theming():
    """
    Add directories and relevant paths to settings for comprehensive theming.
    """
    for theme in get_themes():
        locale_dir = theme.path / "conf" / "locale"
        if locale_dir.isdir():
            settings.LOCALE_PATHS = (locale_dir, ) + settings.LOCALE_PATHS

        if theme.themes_base_dir not in settings.MAKO_TEMPLATES['main']:
            settings.MAKO_TEMPLATES['main'].insert(0, theme.themes_base_dir)
