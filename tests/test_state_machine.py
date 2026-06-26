from datetime import datetime, timezone

import pytest

from paraglider import Paraglider


@pytest.fixture
def paraglider():
    cfg = {
        'name': 'Test Pilot',
        'puretrack_key': 'test-key',
        'discord_id': 123,
        'phone_number': '+33600000000',
        'email': 'test@example.com',
    }
    instance = Paraglider(cfg)
    yield instance
    instance.cleanup()


def test_initial_state(paraglider):
    assert paraglider.state == 'Clearance'


def test_clearance_transition(paraglider):
    paraglider.flying()
    paraglider._speed = 0.1
    paraglider._avg_speed = 0.1
    paraglider._altitude_gnd_calc = 10
    paraglider.update({
        'datetime': datetime.now(timezone.utc),
        'coordinates': (0.0, 0.0),
        'course': 0.0,
        'altitude_gnd_calc': 10.0,
        'speed': 0.1,
        'avg_speed': 0.1,
    })
    assert paraglider.state == 'Clearance'


def test_landing_confirmation_transition(paraglider):
    paraglider.clearance.send(paraglider, message='clearance')
    paraglider.landingConfirmed()
    assert paraglider.state == 'Landed'
