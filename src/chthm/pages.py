"""Blank pages and native color-scheme preferences shared by browsers."""

import re


def color_scheme(background):
    """Advertise the light/dark preference that fits the theme background."""
    red, green, blue = (int(background[index:index + 2], 16) for index in (1, 3, 5))
    return "dark" if 299 * red + 587 * green + 114 * blue < 128000 else "light"


def blank_page_html(background, foreground):
    if not all(isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value)
               for value in (background, foreground)):
        raise ValueError('Blank-page colors must have the form #RRGGBB')
    return f'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="only light">
<title></title>
<style>
html, body {{
    margin: 0;
    width: 100%;
    min-height: 100vh;
    background-color: {background};
    color: {foreground};
    overflow: hidden;
}}
</style>
</head>
<body></body>
</html>
'''


