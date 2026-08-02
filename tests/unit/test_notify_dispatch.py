from boardwatch.notify.channel import DeliveryResult
from boardwatch.notify.dispatch import dispatch


class _Ok:
    name = "ok"

    def deliver(self, items):
        return DeliveryResult("ok", True, "sent")


class _Fail:
    name = "fail"

    def deliver(self, items):
        return DeliveryResult("fail", False, "nope")


class _Raise:
    name = "boom"

    def deliver(self, items):
        raise RuntimeError("kaboom")


def test_dispatch_any_delivered_and_contains_raises():
    out = dispatch((), [_Ok(), _Fail(), _Raise()])
    assert out.any_delivered is True
    names = {r.channel: r.ok for r in out.results}
    assert names == {"ok": True, "fail": False, "boom": False}


def test_dispatch_all_fail_not_delivered():
    out = dispatch((), [_Fail(), _Raise()])
    assert out.any_delivered is False
