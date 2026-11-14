"""Offline blank HTML pages shared by browser integrations."""

import re


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


