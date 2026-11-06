import re

from django import template
from django.utils.html import escape, linebreaks
from django.utils.safestring import mark_safe

register = template.Library()
_FENCE = re.compile(r"```[a-zA-Z0-9]*\n?(.*?)```", re.S)


@register.filter
def rich(text):
    """Escape user text, keep line breaks, and render ```code``` blocks as <pre>."""
    out, last = [], 0
    for m in _FENCE.finditer(text or ""):
        before = text[last:m.start()].strip("\n")
        if before.strip():
            out.append(linebreaks(escape(before)))
        out.append(f"<pre><code>{escape(m.group(1).rstrip())}</code></pre>")
        last = m.end()
    rest = (text or "")[last:].strip("\n")
    if rest.strip():
        out.append(linebreaks(escape(rest)))
    return mark_safe("".join(out))


@register.filter
def initial(user):
    if not user:
        return "?"
    name = user.get_full_name() or user.username
    return (name[:1] or "?").upper()


@register.filter
def plain(text):
    """One-line preview: drop the ``` fences but keep the words."""
    return " ".join(re.sub(r"```[a-zA-Z0-9]*", " ", text or "").split())
