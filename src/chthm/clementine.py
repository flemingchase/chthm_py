"""Compatibility for Clementine versions which replace the platform palette."""

import struct
from .integrations import ini_section_text


def qt_color(color):
    channels = [int(color[i:i + 2], 16) * 257 for i in (1, 3, 5)]
    payload = struct.pack('>IB5H', 67, 1, 65535, *channels, 0)
    return '@Variant(' + ''.join(f'\\x{byte:02x}' for byte in payload) + ')'


def clementine_text(text, values):
    return ini_section_text(text, 'Appearance', {
        'background-color': qt_color(values['CHTHM_BACKGROUND']),
        'foreground-color': qt_color(values['CHTHM_FOREGROUND']),
        'use-custom-set': 'true',
    })
