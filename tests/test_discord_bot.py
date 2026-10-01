import asyncio
from types import SimpleNamespace

import discord
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

    async def post_message_to_channel(channel_id, message, embed=None):
        sent_messages.append((message, embed))
        return 99 + len(sent_messages)

    bot.post_message_to_channel = post_message_to_channel

    await bot.post_waiting_landing_confirmation(
        7,
        '⚠️ Alert for [Pilot]\nPhone: +33123456789',
        'X-pilot',
        mention_first=False,
        notification_type='alert',
    )

    assert len(sent_messages) == 2
    details_content, embed = sent_messages[0]
    prompt_content, prompt_embed = sent_messages[1]
    assert details_content is None
    assert prompt_content == (
        '<@7> Please reply to this message:\n'
        '👍 = I am safe and have landed.\n'
        '👎 = I need assistance or I am not safe.'
    )
    assert prompt_embed is None
    assert embed.title == 'ALERT - NO RESPONSE'
    assert embed.color.value == 0xD97706
    assert embed.description == '⚠️ Alert for [Pilot]\nPhone: +33123456789'
    assert bot.landing_to_be_confirmed[100] is bot.landing_to_be_confirmed[101]
    assert bot.landing_to_be_confirmed[100]['paraglider_key'] == 'X-pilot'


@pytest.mark.asyncio
async def test_confirmation_embed_registers_channel_and_dm_ids_together():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot.channel_id = 55
    bot.send_confirmation_dm = True
    bot.landing_to_be_confirmed = {}
    bot.msg_confirmation_instructions = (
        "Please reply to this message:\n"
        "👍 = I am safe and have landed.\n"
        "👎 = I need assistance or I am not safe."
    )
    bot._ready_event = asyncio.Event()
    bot._ready_event.set()
    bot.is_ready = lambda: True
    bot._pending_confirmation_events = asyncio.Queue()
    bot._cleanup_expired_confirmations = lambda: None
    sent_channel = []
    sent_dm = []

    async def post_message_to_channel(channel_id, message, embed=None):
        sent_channel.append((channel_id, message, embed))
        return 99 + len(sent_channel)

    class FakeUser:
        async def send(self, message=None, embed=None):
            sent_dm.append((message, embed))
            return SimpleNamespace(id=101 + len(sent_dm))

    async def post_bye(discord_id):
        return None

    bot.post_message_to_channel = post_message_to_channel
    bot.get_user = lambda discord_id: FakeUser()
    bot.post_bye = post_bye

    message_id = await bot.post_waiting_landing_confirmation(
        7,
        'Pilot landed near the ridge.',
        'X-pilot',
        notification_type='clearance',
    )

    assert message_id == 100
    assert len(sent_channel) == 2
    assert sent_channel[0][0:2] == (55, None)
    assert sent_channel[0][2].title == 'LANDING CHECK'
    assert sent_channel[0][2].color.value == 0x2ECC71
    assert sent_channel[1] == (
        55,
        '<@7> Please reply to this message:\n'
        '👍 = I am safe and have landed.\n'
        '👎 = I need assistance or I am not safe.',
        None,
    )
    assert sent_dm[0][0] is None
    assert sent_dm[0][1] is sent_channel[0][2]
    assert sent_dm[1] == (bot.msg_confirmation_instructions, None)
    confirmation = bot.landing_to_be_confirmed[100]
    assert all(bot.landing_to_be_confirmed[msg_id] is confirmation for msg_id in (101, 102, 103))
    assert confirmation['message_ids'] == {100, 101, 102, 103}

    await bot._handle_reaction_confirmation(101, 7, '👍', 'Pilot')

    event = await bot._pending_confirmation_events.get()
    assert event['type'] == 'landing_confirmed'
    assert event['paraglider_key'] == 'X-pilot'
    assert bot.landing_to_be_confirmed == {}


@pytest.mark.asyncio
async def test_startup_notification_uses_neutral_embed():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot.channel_id = 55
    bot._ready_event = asyncio.Event()
    bot._ready_event.set()
    bot.is_ready = lambda: True
    sent = []

    async def post_message_to_channel(channel_id, message, embed=None):
        sent.append((channel_id, message, embed))
        return 100

    bot.post_message_to_channel = post_message_to_channel

    message_id = await bot.send_message_async('I\'m connected. Stay safe.', notification_type='startup')

    assert message_id == 100
    assert sent[0][0:2] == (55, None)
    assert sent[0][2].title == 'GUARDIAN ANGEL ONLINE'
    assert sent[0][2].color.value == 0x7F8C8D
    assert sent[0][2].description == 'I\'m connected. Stay safe.'


@pytest.mark.asyncio
async def test_shutdown_notification_uses_neutral_embed():
    bot = DiscordBot.__new__(DiscordBot)
    bot._shutdown_message_sent = False
    bot.msg_good_bye = 'I will be back soon. Stay safe.'
    bot.is_ready = lambda: True
    sent_types = []

    async def send_message(message, notification_type=None):
        sent_types.append(notification_type)
        return 100

    bot.send_message_async = send_message

    message_id = await bot.send_shutdown_message()

    assert message_id == 100
    assert sent_types == ['shutdown']


@pytest.mark.asyncio
async def test_assistance_notification_uses_red_embed():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot.channel_id = 55
    bot._ready_event = asyncio.Event()
    bot._ready_event.set()
    bot.is_ready = lambda: True
    sent = []

    async def post_message_to_channel(channel_id, message, embed=None):
        sent.append((channel_id, message, embed))
        return 100

    bot.post_message_to_channel = post_message_to_channel

    await bot.send_message_async(
        'Assistance requested for Pilot.',
        notification_type='assistance',
    )

    assert sent[0][0:2] == (55, None)
    assert sent[0][2].title == 'ASSISTANCE REQUESTED'
    assert sent[0][2].color.value == 0xC0392B


@pytest.mark.asyncio
async def test_confirmation_prompt_waits_for_embed_rate_limit_retry():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot.channel_id = 55
    bot._send_max_retries = 2
    bot._send_base_backoff = 0
    bot.send_confirmation_dm = False
    bot.landing_to_be_confirmed = {}
    bot.msg_confirmation_instructions = 'Reply with 👍 or 👎.'
    bot._ready_event = asyncio.Event()
    bot._ready_event.set()
    bot.is_ready = lambda: True
    send_order = []

    class FakeChannel:
        id = 55
        embed_attempts = 0

        async def send(self, message=None, embed=None):
            if embed is not None:
                self.embed_attempts += 1
                send_order.append('embed')
                if self.embed_attempts == 1:
                    response = SimpleNamespace(status=429, reason='Too Many Requests')
                    error = discord.HTTPException(response, 'rate limited')
                    error.retry_after = 0
                    raise error
                return SimpleNamespace(id=100)

            send_order.append('prompt')
            return SimpleNamespace(id=101)

    bot.get_channel = lambda channel_id: FakeChannel()

    await bot.post_waiting_landing_confirmation(
        7,
        'Alert details for Pilot.',
        'X-pilot',
        notification_type='alert',
    )

    assert send_order == ['embed', 'embed', 'prompt']
    assert bot.landing_to_be_confirmed[100] is bot.landing_to_be_confirmed[101]


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
async def test_invalid_reaction_gets_response_and_keeps_new_message_linked():
    bot = DiscordBot.__new__(DiscordBot)
    bot._connection = SimpleNamespace(user=SimpleNamespace(id=42))
    bot.logger = get_logger('test')
    bot.channel_id = 55
    bot.msg_unrecognized_response = '⚠️ {mention}, response not recognized.'
    confirmation = {'discord_id': 7, 'paraglider_key': 'X-pilot'}
    bot.landing_to_be_confirmed = {100: confirmation}
    bot._cleanup_expired_confirmations = lambda: None
    sent_messages = []

    async def post_message_to_channel(channel_id, message):
        sent_messages.append((channel_id, message))
        return 101

    bot.post_message_to_channel = post_message_to_channel

    await bot.on_raw_reaction_add(SimpleNamespace(
        user_id=7,
        message_id=100,
        emoji='❓',
    ))

    assert sent_messages == [(55, '⚠️ <@7>, response not recognized.')]
    assert bot.landing_to_be_confirmed[100] is confirmation
    assert bot.landing_to_be_confirmed[101] is confirmation


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


@pytest.mark.asyncio
async def test_confirmation_ttl_cleanup_runs_on_text_reply_path():
    bot = DiscordBot.__new__(DiscordBot)
    bot_user = SimpleNamespace(id=42)
    bot._connection = SimpleNamespace(user=bot_user)
    bot.logger = get_logger('test')
    bot.channel_id = 55
    bot._pending_confirmation_ttl = 1
    bot.landing_to_be_confirmed = {
        100: {
            'discord_id': 7,
            'paraglider_key': 'X-pilot',
            'created_at': asyncio.get_running_loop().time() - 10,
        },
    }
    bot._pending_confirmation_events = asyncio.Queue()

    async def process_commands(message):
        return None

    bot.process_commands = process_commands

    await bot.on_message(SimpleNamespace(
        author=SimpleNamespace(id=7, name='Pilot'),
        content='yes',
        reference=SimpleNamespace(
            resolved=SimpleNamespace(id=100, author=bot_user),
        ),
    ))

    assert bot._pending_confirmation_events.empty()
    assert 100 not in bot.landing_to_be_confirmed


@pytest.mark.asyncio
async def test_two_pending_confirmations_both_get_bye_on_thumbs_up():
    """First ack must not wipe the second pilot's pending confirmation."""
    bot = DiscordBot.__new__(DiscordBot)
    bot._connection = SimpleNamespace(user=SimpleNamespace(id=42))
    bot.logger = get_logger('test')
    bot.channel_id = 55
    bot._pending_confirmation_ttl = 300
    first = {
        'discord_id': 7,
        'paraglider_key': 'X-first',
        'created_at': asyncio.get_running_loop().time(),
        'message_ids': {100},
    }
    second = {
        'discord_id': 8,
        'paraglider_key': 'X-second',
        'created_at': asyncio.get_running_loop().time(),
        'message_ids': {101},
    }
    bot.landing_to_be_confirmed = {100: first, 101: second}
    bot._pending_confirmation_events = asyncio.Queue()
    bot._cleanup_expired_confirmations = lambda: None
    byes = []

    async def post_bye(discord_id):
        byes.append(discord_id)

    bot.post_bye = post_bye

    await bot.on_raw_reaction_add(SimpleNamespace(
        user_id=7,
        message_id=100,
        emoji='👍',
    ))
    await bot.on_raw_reaction_add(SimpleNamespace(
        user_id=8,
        message_id=101,
        emoji='👍',
    ))

    events = [
        await bot._pending_confirmation_events.get(),
        await bot._pending_confirmation_events.get(),
    ]
    assert byes == [7, 8]
    assert [event['paraglider_key'] for event in events] == ['X-first', 'X-second']
    assert bot.landing_to_be_confirmed == {}


@pytest.mark.asyncio
async def test_thumbs_up_with_skin_tone_is_accepted():
    bot = DiscordBot.__new__(DiscordBot)
    bot._connection = SimpleNamespace(user=SimpleNamespace(id=42))
    bot.logger = get_logger('test')
    bot.landing_to_be_confirmed = {
        100: {
            'discord_id': '7',
            'paraglider_key': 'X-pilot',
            'created_at': asyncio.get_running_loop().time(),
            'message_ids': {100},
        },
    }
    bot._pending_confirmation_events = asyncio.Queue()
    bot._cleanup_expired_confirmations = lambda: None
    byes = []

    async def post_bye(discord_id):
        byes.append(discord_id)

    bot.post_bye = post_bye

    await bot.on_raw_reaction_add(SimpleNamespace(
        user_id=7,
        message_id=100,
        emoji='👍🏻',
    ))

    event = await bot._pending_confirmation_events.get()
    assert event['type'] == 'landing_confirmed'
    assert event['discord_id'] == 7
    assert byes == [7]


@pytest.mark.asyncio
async def test_check_command_uses_bot_puretrack_group():
    sent = []

    class FakeCtx:
        bot = SimpleNamespace(puretrack_grp='batouchoncel')

        async def send(self, message):
            sent.append(message)

    from discord_bot import check

    await check.callback(FakeCtx(), member=SimpleNamespace(mention='@Pilot'))

    assert 'group=batouchoncel' in sent[0]
