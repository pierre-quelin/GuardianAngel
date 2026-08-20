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
        content='oui',
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
