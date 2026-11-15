"""Native website preferences and a theme-colored blank page for qutebrowser."""

import ast
import io
from pathlib import Path
import tokenize

from .pages import color_scheme

BEGIN = '# >>> chthm qutebrowser blank page >>>'
END = '# <<< chthm qutebrowser blank page <<<'


def blank_page_pattern(filename):
    # qutebrowser matches patterns against decoded paths. Escape glob syntax,
    # and match a single path character for URL delimiters (# and ?) which its
    # pattern parser would otherwise treat as fragments or query strings.
    escapes = {"*": "[*]", "[": "[[]", "]": "[]]", "#": "[!/]", "?": "[!/]"}
    path = Path(filename).absolute().as_posix()
    return "file://" + "".join(escapes.get(char, char) for char in path)


def blank_page_config(text, filename, background=None):
    """Keep native preferences and blank-page settings after user assignments."""
    if not text.strip():
        text = 'config.load_autoconfig()\n'
    uri = Path(filename).absolute().as_uri()
    pattern = blank_page_pattern(filename)
    website = ''
    if background is not None:
        website = f'''# Let websites choose their own colors; advertise only a light/dark preference.
# Keep the native fallback: a dark canvas alone leaves unstyled text black.
config.set("colors.webpage.bg", "white")
config.set("colors.webpage.preferred_color_scheme", {color_scheme(background)!r})
config.set("colors.webpage.darkmode.enabled", False)
'''
    block = f'''{BEGIN}
config.set("url.default_page", {uri!r})
config.set("url.start_pages", [{uri!r}])
config.set("colors.webpage.darkmode.enabled", False, pattern={pattern!r})
{website}{END}
'''
    lines = text.splitlines(keepends=True)
    try:
        ast.parse(text, filename='qutebrowser/config.py')
        markers = [(token.string, token.start[0] - 1) for token in
                   tokenize.generate_tokens(io.StringIO(text).readline)
                   if token.type == tokenize.COMMENT and token.start[1] == 0]
        starts = [line for comment, line in markers if comment == BEGIN]
        ends = [line for comment, line in markers if comment == END]
        if len(starts) != len(ends) or len(starts) > 1 or (starts and starts[0] >= ends[0]):
            raise ValueError('Malformed qutebrowser blank-page markers')
        if starts:
            # Keep the managed settings last even if the user appended settings.
            text = ''.join(lines[:starts[0]]) + ''.join(lines[ends[0] + 1:])
        updated = text + ('\n' if text and not text.endswith('\n') else '') + block
        compile(updated, 'qutebrowser/config.py', 'exec')
        return updated
    except (SyntaxError, tokenize.TokenError) as error:
        raise ValueError(f'qutebrowser config.py syntax check failed: {error}') from error
