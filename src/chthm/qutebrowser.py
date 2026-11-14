"""A local, theme-colored blank page and a small qutebrowser settings block."""

import ast
import io
from pathlib import Path
import tokenize

BEGIN = '# >>> chthm qutebrowser blank page >>>'
END = '# <<< chthm qutebrowser blank page <<<'


def blank_page_pattern(filename):
    # qutebrowser matches patterns against decoded paths. Escape glob syntax,
    # and match a single path character for URL delimiters (# and ?) which its
    # pattern parser would otherwise treat as fragments or query strings.
    escapes = {"*": "[*]", "[": "[[]", "]": "[]]", "#": "[!/]", "?": "[!/]"}
    path = Path(filename).absolute().as_posix()
    return "file://" + "".join(escapes.get(char, char) for char in path)


def blank_page_config(text, filename):
    """Override only the blank-page settings, after existing user assignments."""
    if not text.strip():
        text = 'config.load_autoconfig()\n'
    uri = Path(filename).absolute().as_uri()
    pattern = blank_page_pattern(filename)
    block = f'''{BEGIN}
config.set("url.default_page", {uri!r})
config.set("url.start_pages", [{uri!r}])
config.set("colors.webpage.darkmode.enabled", False, pattern={pattern!r})
{END}
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
