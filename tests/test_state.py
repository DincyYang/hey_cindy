import fakeredis
import redis
import pytest

from cloud.state import LightState


class TestLightState:
    def test_default_is_off(self):
        ls = LightState(client=fakeredis.FakeStrictRedis(decode_responses=True))
        assert ls.get() == "off"

    def test_set_then_get(self):
        ls = LightState(client=fakeredis.FakeStrictRedis(decode_responses=True))
        ls.set("on")
        assert ls.get() == "on"

    def test_falls_back_to_memory_when_redis_down(self):
        class BrokenRedis:
            def get(self, *a, **k):
                raise redis.RedisError("down")
            def set(self, *a, **k):
                raise redis.RedisError("down")

        ls = LightState(client=BrokenRedis())
        ls.set("on")              # write fails, but in-memory copy is kept
        assert ls.get() == "on"   # read falls back to in-memory copy
