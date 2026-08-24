from rich.console import Console

from boardwatch.cli._hints import print_next_step


def test_print_next_step_prefixes_each_line_with_an_arrow() -> None:
    console = Console(width=200, force_terminal=False, no_color=True)
    with console.capture() as cap:
        print_next_step(console, "run `boardwatch top`", "then `boardwatch show <#>`")
    out = cap.get()
    assert "→ run `boardwatch top`" in out
    assert "→ then `boardwatch show <#>`" in out
