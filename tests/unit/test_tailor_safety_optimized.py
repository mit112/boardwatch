from __future__ import annotations

import subprocess
import sys
import textwrap


def test_guard_raises_under_optimized_mode() -> None:
    # `assert` would be stripped by -O; an explicit raise must survive.
    code = textwrap.dedent(
        """
        from boardwatch.tailor.model import Resume, Entry, Bullet
        from boardwatch.tailor.plan import TailorPlan
        from boardwatch.tailor.equivalences import load_equivalences
        from boardwatch.tailor.safety import enforce_tier_a, TierASafetyError
        m = Resume(header=["h"], education=[], skill_groups=[], entries=[Entry(entry_id="e1", heading="H",
            bullets=[Bullet(bullet_id="b1", text="Shipped JS")])])
        bad = m.model_copy(update={"header": ["x"]})
        try:
            enforce_tier_a(m, bad, TailorPlan(ops=()), load_equivalences()); print("NO_RAISE")
        except TierASafetyError:
            print("RAISED")
        """
    )
    out = subprocess.run(
        [sys.executable, "-O", "-c", code], capture_output=True, text=True
    )
    assert out.stdout.strip() == "RAISED", out.stderr
