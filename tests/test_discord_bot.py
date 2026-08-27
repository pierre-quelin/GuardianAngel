import asyncio
from types import SimpleNamespace

import pytest

from discord_bot import DiscordBot
from logger import get_logger


@pytest.mark.asyncio
async def test_reply_to_landing_confirmation_is_accepted():
    bot = DiscordBot.__new__(DiscordBot)
    bot_user = SimpleNamespace(id=42)
    bot._connection = SimpleNamespace(user=bot_user)
    bot.logger = get_logger('test')
    bot.landing_to_be_confirmed = {100: {'discord_id': 7}}
    bot._pending_confirmation_events = asyncio.Queue()
    sent_replies = []

    async def post_bye(discord_id):
        sent_replies.append(discord_id)

    async def process_commands(message):
        return None

    bot.post_bye = post_bye
    bot.process_commands = process_commands

    message = SimpleNamespace(
        author=SimpleNamespace(id=7, name='Pilot'),
        content='I am safe and have landed',
        reference=SimpleNamespace(
            resolved=SimpleNamespace(id=100, author=bot_user),
        ),
    )

    await bot.on_message(message)

    event = await bot._pending_confirmation_events.get()
    assert event['type'] == 'landing_confirmed'
    assert event['discord_id'] == 7
    assert event['paraglider_key'] is None
    assert sent_replies == [7]
    assert 100 not in bot.landing_to_be_confirmed


@pytest.mark.asyncio
async def test_landing_confirmation_message_is_registered():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot.channel_id = 55
    bot.landing_to_be_confirmed = {}
    bot.msg_confirmation_instructions = (
        "Please reply to this message:\n"
        "👍 = I am safe and have landed.\n"
        "👎 = I need assistance or I am not safe."
    )
    bot._ready_event = asyncio.Event()
    bot._ready_event.set()
    bot.is_ready = lambda: True

    async def post_message_to_channel(channel_id, message):
        assert channel_id == 55
        assert message.startswith('<@7> ')
        return 100

    bot.post_message_to_channel = post_message_to_channel

    message_id = await bot.post_waiting_landing_confirmation(7, 'Are you safe?', 'X-pilot')

    assert message_id == 100
    assert bot.landing_to_be_confirmed[100]['discord_id'] == 7
    assert bot.landing_to_be_confirmed[100]['paraglider_key'] == 'X-pilot'


@pytest.mark.asyncio
async def test_bye_message_places_mention_after_checkmark():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot.channel_id = 55
    bot.msg_bye = '✅ Thank you {mention}. Your response has been recorded.'
    sent_messages = []

    async def post_message_to_channel(channel_id, message):
        sent_messages.append((channel_id, message))

    bot.post_message_to_channel = post_message_to_channel

    await bot.post_bye(7)

    assert sent_messages == [
        (55, '✅ Thank you <@7>. Your response has been recorded.'),
    ]


@pytest.mark.asyncio
async def test_alert_confirmation_places_mention_before_instructions():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot.channel_id = 55
    bot.msg_confirmation_instructions = (
        "Please reply to this message:\n"
        "👍 = I am safe and have landed.\n"
        "👎 = I need assistance or I am not safe."
    )
    bot.landing_to_be_confirmed = {}
    bot._ready_event = asyncio.Event()
    bot._ready_event.set()
    bot.is_ready = lambda: True
    sent_messages = []

    async def post_message_to_channel(channel_id, message):
        sent_messages.append(message)
        return 100

    bot.post_message_to_channel = post_message_to_channel

    await bot.post_waiting_landing_confirmation(
        7,
        '⚠️ Alert for [Pilot]\nPhone: +33123456789',
        'X-pilot',
        mention_first=False,
    )

    assert sent_messages == [
        '⚠️ Alert for [Pilot]\nPhone: +33123456789\n\n'
        '<@7> Please reply to this message:\n'
        '👍 = I am safe and have landed.\n'
        '👎 = I need assistance or I am not safe.'
    ]


@pytest.mark.asyncio
async def test_raw_reaction_confirms_pending_landing():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot._connection = SimpleNamespace(user=SimpleNamespace(id=42))
    bot.landing_to_be_confirmed = {
        100: {'discord_id': 7, 'paraglider_key': 'X-pilot'},
    }
    bot._pending_confirmation_events = asyncio.Queue()
    sent_replies = []

    async def post_bye(discord_id):
        sent_replies.append(discord_id)

    bot.post_bye = post_bye
    bot._cleanup_expired_confirmations = lambda: None

    await bot.on_raw_reaction_add(SimpleNamespace(
        user_id=7,
        message_id=100,
        emoji='👍',
    ))

    event = await bot._pending_confirmation_events.get()
    assert event['paraglider_key'] == 'X-pilot'
    assert sent_replies == [7]
    assert 100 not in bot.landing_to_be_confirmed


@pytest.mark.asyncio
async def test_thumbs_down_rejects_confirmation_without_replying_bye():
    bot = DiscordBot.__new__(DiscordBot)
    bot._connection = SimpleNamespace(user=SimpleNamespace(id=42))
    bot.logger = get_logger('test')
    bot.channel_id = 55
    bot.msg_negative_response = 'The alert remains active.'
    bot.landing_to_be_confirmed = {
        100: {'discord_id': 7, 'paraglider_key': 'X-pilot'},
    }
    bot._pending_confirmation_events = asyncio.Queue()
    bot._cleanup_expired_confirmations = lambda: None

    async def post_bye(discord_id):
        raise AssertionError('A negative response must not send a success reply')

    bot.post_bye = post_bye

    negative_replies = []

    async def post_negative_acknowledgment(discord_id):
        negative_replies.append(discord_id)

    bot.post_negative_acknowledgment = post_negative_acknowledgment

    await bot.on_raw_reaction_add(SimpleNamespace(
        user_id=7,
        message_id=100,
        emoji='👎',
    ))

    event = await bot._pending_confirmation_events.get()
    assert event['type'] == 'landing_rejected'
    assert event['paraglider_key'] == 'X-pilot'
    assert negative_replies == [7]
    assert 100 not in bot.landing_to_be_confirmed


@pytest.mark.asyncio
async def test_negative_text_rejects_confirmation_and_sends_acknowledgment():
    bot = DiscordBot.__new__(DiscordBot)
    bot_user = SimpleNamespace(id=42)
    bot._connection = SimpleNamespace(user=bot_user)
    bot.logger = get_logger('test')
    bot.landing_to_be_confirmed = {100: {'discord_id': 7, 'paraglider_key': 'X-pilot'}}
    bot._pending_confirmation_events = asyncio.Queue()
    bot.channel_id = 55
    bot.msg_negative_response = 'The alert remains active.'
    bot.post_message_to_channel = lambda channel_id, message: None
    acknowledgments = []

    async def post_negative_acknowledgment(discord_id):
        acknowledgments.append(discord_id)

    async def process_commands(message):
        return None

    bot.post_negative_acknowledgment = post_negative_acknowledgment
    bot.process_commands = process_commands

    await bot.on_message(SimpleNamespace(
        author=SimpleNamespace(id=7, name='Pilot'),
        content='I need assistance',
        reference=SimpleNamespace(
            resolved=SimpleNamespace(id=100, author=bot_user),
        ),
    ))

    event = await bot._pending_confirmation_events.get()
    assert event['type'] == 'landing_rejected'
    assert acknowledgments == [7]
    assert 100 not in bot.landing_to_be_confirmed
