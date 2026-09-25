"""Parse the YAML files this package ships, with libyaml when it is installed.

`yaml.CSafeLoader` is `SafeLoader`'s constructor and resolver over libyaml's scanner and parser.
On every YAML file in the package the two produce the same object, and
`tests/unit/test_yamlio.py` loads each file both ways to keep it so. On arbitrary text they are
NOT the same parser. libyaml accepts a tab as separation space, a `#` comment touching a block
scalar header, and a `?` inside a flow plain scalar, all of which the pure parser refuses. It reads
an empty `!`-tagged scalar as `''` where the pure parser reads `None`, and it skips a BOM at the
start of any line rather than only the first. Text a user wrote (an override, a résumé, an answers
file) therefore keeps plain `yaml.safe_load`, so a file that was refused yesterday is not accepted
today. Only the package's own files, whose content that test pins, come through here.
"""

from __future__ import annotations

from typing import Any

import yaml


def load_bundled(text: str) -> Any:
    """`yaml.safe_load(text)` for a file shipped in the package, parsed by libyaml if present.

    The check runs per call, not at import, so the pure fallback is testable, and `CSafeLoader`
    is named only when it exists: without libyaml, `yaml` does not define it.
    """
    loader = yaml.CSafeLoader if yaml.__with_libyaml__ else yaml.SafeLoader
    return yaml.load(text, Loader=loader)
