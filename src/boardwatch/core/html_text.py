"""HTML → text behind selectolax (§3.3, §6.3-6).

Block-level elements produce line separators; inline tags merge into contiguous
text; entities are decoded by the parser. Basic correctness only is P0 — the
malformed-HTML fidelity suite is owned by P2 (§6.3-6); no robustness beyond
what selectolax gives for free.
"""

from __future__ import annotations

from selectolax.parser import HTMLParser, Node

_BLOCK_TAGS = frozenset(
    {
        "p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
        "br", "table", "tr", "th", "td", "section", "article", "blockquote",
        "pre", "header", "footer", "hr",
    }
)
_DROP_TAGS = frozenset({"script", "style"})


def html_to_text(html: str) -> str:
    if not html or not html.strip():
        return ""
    tree = HTMLParser(html)
    root = tree.body if tree.body is not None else tree.root
    if root is None:
        return ""
    parts: list[str] = []
    _collect(root, parts)
    lines = (" ".join(chunk.split()) for chunk in "".join(parts).split("\n"))
    return "\n".join(line for line in lines if line)


def _collect(node: Node, parts: list[str]) -> None:
    child = node.child
    while child is not None:
        if child.tag == "-text":
            parts.append((child.text_content or "").replace("\n", " "))
        elif child.tag not in _DROP_TAGS:
            is_block = child.tag in _BLOCK_TAGS
            if is_block:
                parts.append("\n")
            _collect(child, parts)
            if is_block:
                parts.append("\n")
        child = child.next
