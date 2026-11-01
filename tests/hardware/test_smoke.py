"""Smoke tests against the real devices. Excluded by default (see pyproject addopts); run with
``PASR_HW_TESTS=1 uv run pytest -m hardware`` while the robot is connected."""

import os

import pytest

from pasr.hardware.check import check_devices
from pasr.settings.loader import load_settings

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(not os.environ.get("PASR_HW_TESTS"), reason="set PASR_HW_TESTS=1"),
]


@pytest.mark.parametrize("device", ["ohbot", "speaker", "watch"])
async def test_device_check_passes(device):
    settings = load_settings(explicit={"hardware": {"mode": "real"}})
    (report,) = await check_devices(settings, only=[device])
    assert report.ok, report.detail
