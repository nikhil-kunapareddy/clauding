"""The Claude spark mark, used as the menu bar icon.

Rasterized from claude.ai's SVG favicon to a 60x60 alpha mask, so it can be tinted at
runtime rather than shipped once per colour. Carried over unchanged from the Swift
implementation this tool replaces (see ACKNOWLEDGEMENTS.md).
"""

import base64

_SPARK_PNG_BASE64 = (
    "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"
    "AA3aE4hGmknVAAAAAElFTkSuQmCC"
)


def spark_png() -> bytes:
    """The mark as raw PNG bytes."""
    return base64.b64decode(_SPARK_PNG_BASE64)
