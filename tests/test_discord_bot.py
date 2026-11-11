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
    bot._cleanup_expired_confirmations = lambda: None
    bot._positive_reaction_emojis = DiscordBot._POSITIVE_REACTION_EMOJIS
    bot._negative_reaction_emojis = DiscordBot._NEGATIVE_REACTION_EMOJIS
    sent_replies = []

    async def post_bye(discord_id, actor_role="pilot"):
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


def test_normalize_reply_text_strips_trailing_punctuation_and_emoji_variants():
    assert DiscordBot._normalize_reply_text('I am safe and have landed.') == (
        'i am safe and have landed'
    )
    assert DiscordBot._normalize_reply_text('👍️') == '👍'
    assert DiscordBot._normalize_reply_text('👍🏻') == '👍'


@pytest.mark.asyncio
async def test_reply_with_trailing_period_is_accepted():
    bot = DiscordBot.__new__(DiscordBot)
    bot_user = SimpleNamespace(id=42)
    bot._connection = SimpleNamespace(user=bot_user)
    bot.logger = get_logger('test')
    bot.landing_to_be_confirmed = {100: {'discord_id': 7, 'paraglider_key': 'X-pilot'}}
    bot._pending_confirmation_events = asyncio.Queue()
    bot._cleanup_expired_confirmations = lambda: None
    bot._positive_reaction_emojis = DiscordBot._POSITIVE_REACTION_EMOJIS
    bot._negative_reaction_emojis = DiscordBot._NEGATIVE_REACTION_EMOJIS
    sent_replies = []

    async def post_bye(discord_id, actor_role="pilot"):
        sent_replies.append(discord_id)

    bot.post_bye = post_bye

    async def process_commands(message):
        return None

    bot.process_commands = process_commands

    await bot.on_message(SimpleNamespace(
        author=SimpleNamespace(id=7, name='Pilot'),
        content='I am safe and have landed.',
        reference=SimpleNamespace(
            resolved=SimpleNamespace(id=100, author=bot_user),
        ),
    ))

    event = await bot._pending_confirmation_events.get()
    assert event['type'] == 'landing_confirmed'
    assert sent_replies == [7]


@pytest.mark.asyncio
async def test_reply_with_thumbs_up_emoji_is_accepted():
    bot = DiscordBot.__new__(DiscordBot)
    bot_user = SimpleNamespace(id=42)
    bot._connection = SimpleNamespace(user=bot_user)
    bot.logger = get_logger('test')
    bot.landing_to_be_confirmed = {100: {'discord_id': 7, 'paraglider_key': 'X-pilot'}}
    bot._pending_confirmation_events = asyncio.Queue()
    bot._cleanup_expired_confirmations = lambda: None
    bot._positive_reaction_emojis = DiscordBot._POSITIVE_REACTION_EMOJIS
    bot._negative_reaction_emojis = DiscordBot._NEGATIVE_REACTION_EMOJIS
    sent_replies = []

    async def post_bye(discord_id, actor_role="pilot"):
        sent_replies.append(discord_id)

    async def process_commands(message):
        return None

    bot.post_bye = post_bye
    bot.process_commands = process_commands

    await bot.on_message(SimpleNamespace(
        author=SimpleNamespace(id=7, name='Pilot'),
        content='👍',
        reference=SimpleNamespace(
            resolved=SimpleNamespace(id=100, author=bot_user),
        ),
    ))

    event = await bot._pending_confirmation_events.get()
    assert event['type'] == 'landing_confirmed'
    assert sent_replies == [7]


@pytest.mark.asyncio
async def test_reply_with_thumbs_down_emoji_is_rejected():
    bot = DiscordBot.__new__(DiscordBot)
    bot_user = SimpleNamespace(id=42)
    bot._connection = SimpleNamespace(user=bot_user)
    bot.logger = get_logger('test')
    bot.landing_to_be_confirmed = {100: {'discord_id': 7, 'paraglider_key': 'X-pilot'}}
    bot._pending_confirmation_events = asyncio.Queue()
    bot._cleanup_expired_confirmations = lambda: None
    bot._positive_reaction_emojis = DiscordBot._POSITIVE_REACTION_EMOJIS
    bot._negative_reaction_emojis = DiscordBot._NEGATIVE_REACTION_EMOJIS
    acknowledgments = []

    async def post_negative_acknowledgment(discord_id):
        acknowledgments.append(discord_id)

    async def process_commands(message):
        return None

    bot.post_negative_acknowledgment = post_negative_acknowledgment
    bot.process_commands = process_commands

    await bot.on_message(SimpleNamespace(
        author=SimpleNamespace(id=7, name='Pilot'),
        content='👎',
        reference=SimpleNamespace(
            resolved=SimpleNamespace(id=100, author=bot_user),
        ),
    ))

    event = await bot._pending_confirmation_events.get()
    assert event['type'] == 'landing_rejected'
    assert acknowledgments == [7]


@pytest.mark.asyncio
async def test_landing_confirmation_message_is_registered():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot.discord_channel_id = 55
    bot.landing_to_be_confirmed = {}
    bot.msg_confirmation_instructions = (
        "To respond, reply to this message or react to it:\n"
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
    bot.discord_channel_id = 55
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
    bot.discord_channel_id = 55
    bot.msg_confirmation_instructions = (
        "To respond, reply to this message or react to it:\n"
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
        '<@7> To respond, reply to this message or react to it:\n'
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
    bot.discord_channel_id = 55
    bot.send_confirmation_dm = True
    bot.landing_to_be_confirmed = {}
    bot.msg_confirmation_instructions = (
        "To respond, reply to this message or react to it:\n"
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

    async def post_bye(discord_id, actor_role="pilot", channel_id=None):
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
        '<@7> To respond, reply to this message or react to it:\n'
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
async def test_alert_embed_stays_in_supervisor_channel_and_prompt_uses_pilot_channel():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot.discord_channel_id = 55
    bot.send_confirmation_dm = False
    bot.landing_to_be_confirmed = {}
    bot.msg_confirmation_instructions = (
        "To respond, reply to this message or react to it:\n"
        "👍 = I am safe and have landed.\n"
        "👎 = I need assistance or I am not safe."
    )
    bot._ready_event = asyncio.Event()
    bot._ready_event.set()
    bot.is_ready = lambda: True
    sent = []

    async def post_message_to_channel(channel_id, message, embed=None):
        sent.append((channel_id, message, embed))
        return 100 + len(sent)

    bot.post_message_to_channel = post_message_to_channel

    await bot.post_waiting_landing_confirmation(
        7,
        'Alert for Pilot',
        'X-pilot',
        mention_first=False,
        notification_type='alert',
        pilot_channel_id=77,
    )

    assert sent[0][0:2] == (55, None)
    assert sent[0][2].title == 'ALERT - NO RESPONSE'
    assert sent[1] == (
        77,
        f'Alert for Pilot\n\n<@7> {bot.msg_confirmation_instructions}',
        None,
    )
    assert set(bot.landing_to_be_confirmed) == {101, 102}
    confirmation = bot.landing_to_be_confirmed[101]
    assert bot.landing_to_be_confirmed[102] is confirmation
    assert confirmation['channel_id'] == 77
    assert confirmation['paraglider_key'] == 'X-pilot'
    assert confirmation['message_ids'] == {101, 102}
    assert confirmation['supervisor_user_ids'] == set()


@pytest.mark.asyncio
async def test_supervisor_can_acknowledge_from_the_group_alert_channel():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot.landing_to_be_confirmed = {
        100: {
            'discord_id': 7,
            'paraglider_key': 'X-pilot',
            'channel_id': 77,
            'supervisor_user_ids': {99},
            'message_ids': {100},
        },
    }
    bot._cleanup_expired_confirmations = lambda: None
    bot._pending_confirmation_events = asyncio.Queue()
    bot._positive_reaction_emojis = DiscordBot._POSITIVE_REACTION_EMOJIS
    bot._negative_reaction_emojis = DiscordBot._NEGATIVE_REACTION_EMOJIS
    acknowledgments = []

    async def post_bye(discord_id, actor_role='pilot', channel_id=None):
        acknowledgments.append((discord_id, actor_role, channel_id))

    bot.post_bye = post_bye

    await bot._handle_reaction_confirmation(
        100, 99, '👍', 'Supervisor', channel_id=55
    )

    event = await bot._pending_confirmation_events.get()
    assert event['actor_role'] == 'supervisor'
    assert event['paraglider_key'] == 'X-pilot'
    assert acknowledgments == [(99, 'supervisor', 55)]


@pytest.mark.asyncio
async def test_alert_acknowledgment_notifies_supervisor_channel():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot.landing_to_be_confirmed = {
        100: {
            'discord_id': 7,
            'paraglider_key': 'X-pilot',
            'pilot_name': 'Pilot',
            'notification_type': 'alert',
            'channel_id': 77,
            'supervisor_channel_id': 55,
            'supervisor_user_ids': {99},
            'message_ids': {100},
        },
    }
    bot._cleanup_expired_confirmations = lambda: None
    bot._pending_confirmation_events = asyncio.Queue()
    bot._positive_reaction_emojis = DiscordBot._POSITIVE_REACTION_EMOJIS
    bot._negative_reaction_emojis = DiscordBot._NEGATIVE_REACTION_EMOJIS
    acknowledged = []

    async def post_bye(discord_id, actor_role='pilot', channel_id=None):
        return None

    async def send_message(message, notification_type=None, channel_id=None):
        acknowledged.append((message, notification_type, channel_id))
        return 101

    bot.post_bye = post_bye
    bot.send_message_async = send_message

    await bot._handle_reaction_confirmation(
        100, 7, '👍', 'Pilot', channel_id=77
    )

    assert acknowledged == [(
        '✅ Alert for **Pilot** acknowledged by pilot <@7>.',
        'acknowledged',
        55,
    )]


@pytest.mark.asyncio
async def test_clearance_confirmation_uses_pilot_channel():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot.discord_channel_id = 55
    bot.send_confirmation_dm = False
    bot.landing_to_be_confirmed = {}
    bot.msg_confirmation_instructions = 'To respond, reply to this message or react to it.'
    bot._ready_event = asyncio.Event()
    bot._ready_event.set()
    bot.is_ready = lambda: True
    sent = []

    async def post_message_to_channel(channel_id, message, embed=None):
        sent.append((channel_id, message, embed))
        return 200 + len(sent)

    bot.post_message_to_channel = post_message_to_channel

    await bot.post_waiting_landing_confirmation(
        7,
        'Pilot has landed. Is everything OK?',
        'X-pilot',
        notification_type='clearance',
        pilot_channel_id=77,
    )

    assert len(sent) == 2
    assert all(item[0] == 77 for item in sent)
    assert sent[0][2].title == 'LANDING CHECK'
    assert sent[0][2].description == 'Pilot has landed. Is everything OK?'
    assert sent[1][1] == (
        '<@7> To respond, reply to this message or react to it.'
    )


@pytest.mark.asyncio
async def test_reaction_acknowledgment_uses_interaction_channel():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot.landing_to_be_confirmed = {
        100: {
            'discord_id': 7,
            'paraglider_key': 'X-pilot',
            'channel_id': 77,
        },
    }
    bot._cleanup_expired_confirmations = lambda: None
    bot._pending_confirmation_events = asyncio.Queue()
    bot._positive_reaction_emojis = DiscordBot._POSITIVE_REACTION_EMOJIS
    bot._negative_reaction_emojis = DiscordBot._NEGATIVE_REACTION_EMOJIS
    acknowledgments = []

    async def post_bye(discord_id, actor_role='pilot', channel_id=None):
        acknowledgments.append((discord_id, actor_role, channel_id))

    bot.post_bye = post_bye

    await bot._handle_reaction_confirmation(100, 7, '👍', 'Pilot', channel_id=77)

    assert acknowledgments == [(7, 'pilot', 77)]
    assert (await bot._pending_confirmation_events.get())['paraglider_key'] == 'X-pilot'


@pytest.mark.asyncio
async def test_assistance_acknowledgment_can_be_cancelled_with_thumbs_up():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot.discord_channel_id = 55
    bot.landing_to_be_confirmed = {
        100: {
            'discord_id': 7,
            'paraglider_key': 'X-pilot',
            'pilot_name': 'Pilot',
            'notification_type': 'clearance',
            'supervisor_channel_id': 55,
            'channel_id': 77,
            'supervisor_user_ids': {99},
            'created_at': 1,
            'message_ids': {100},
            'completed': False,
        },
    }
    bot._cleanup_expired_confirmations = lambda: None
    bot._pending_confirmation_events = asyncio.Queue()
    bot._positive_reaction_emojis = DiscordBot._POSITIVE_REACTION_EMOJIS
    bot._negative_reaction_emojis = DiscordBot._NEGATIVE_REACTION_EMOJIS
    bot.msg_negative_response = (
        "🚨 Your response indicates that you need assistance or are not safe.\n"
        "The alert remains active. The guardian has been notified.\n\n"
        "To update your response, reply to this message or react to it:\n"
        "👍 = I am safe and have landed; clear the alert.\n"
        "👎 = I still need assistance or am not safe."
    )
    sent = []

    async def post_message_to_channel(channel_id, message):
        sent.append((channel_id, message))
        return 200

    async def post_bye(discord_id, actor_role='pilot', channel_id=None):
        return None

    async def notify_supervisor(*args):
        return None

    bot.post_message_to_channel = post_message_to_channel
    bot.post_bye = post_bye
    bot._notify_supervisor_alert_acknowledged = notify_supervisor

    await bot._handle_reaction_confirmation(100, 7, '👎', 'Pilot', channel_id=77)

    assert sent[0][0] == 77
    assert 'not safe.\nThe alert remains active.' in sent[0][1]
    assert '👍 = I am safe and have landed; clear the alert.' in sent[0][1]
    assert bot.landing_to_be_confirmed[200]['notification_type'] == 'alert'

    await bot._handle_reaction_confirmation(200, 7, '👍', 'Pilot', channel_id=77)

    rejected = await bot._pending_confirmation_events.get()
    confirmed = await bot._pending_confirmation_events.get()
    assert rejected['type'] == 'landing_rejected'
    assert confirmed['type'] == 'landing_confirmed'
    assert confirmed['paraglider_key'] == 'X-pilot'
    assert bot.landing_to_be_confirmed == {}


@pytest.mark.asyncio
async def test_supervisor_alert_acknowledgment_also_notifies_pilot_channel():
    bot = DiscordBot.__new__(DiscordBot)
    sent = []

    async def send_message(message, notification_type=None, channel_id=None):
        sent.append((message, notification_type, channel_id))
        return len(sent)

    bot.send_message_async = send_message
    confirmation = {
        'notification_type': 'alert',
        'pilot_name': 'Pilot',
        'pilot_channel_id': 77,
        'channel_id': 77,
        'supervisor_channel_id': 55,
    }

    await bot._notify_supervisor_alert_acknowledged(
        confirmation,
        discord_id=99,
        actor_role='supervisor',
        acknowledgment_channel_id=55,
    )

    assert [message[2] for message in sent] == [55, 77]
    assert 'acknowledged by your angel <@99>' in sent[1][0]
    assert sent[1][1] == 'acknowledged'


@pytest.mark.asyncio
async def test_supervisor_acknowledgment_does_not_duplicate_in_pilot_channel():
    bot = DiscordBot.__new__(DiscordBot)
    sent_channels = []

    async def send_message(message, notification_type=None, channel_id=None):
        sent_channels.append(channel_id)
        return len(sent_channels)

    bot.send_message_async = send_message

    await bot._notify_supervisor_alert_acknowledged(
        {
            'notification_type': 'alert',
            'pilot_name': 'Pilot',
            'pilot_channel_id': 77,
            'channel_id': 77,
            'supervisor_channel_id': 55,
        },
        discord_id=99,
        actor_role='supervisor',
        acknowledgment_channel_id=77,
    )

    assert sent_channels == [55]


@pytest.mark.asyncio
async def test_startup_notification_uses_neutral_embed():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot.discord_channel_id = 55
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
    bot.msg_good_bye = 'I will be back soon.'
    bot.supervisor_channels = [55, 56]
    bot.is_ready = lambda: True
    sent_types = []

    async def send_message(message, notification_type=None, channel_id=None):
        sent_types.append((notification_type, channel_id))
        return 100 + len(sent_types)

    bot.send_message_async = send_message

    message_id = await bot.send_shutdown_message()

    assert message_id == 101
    assert sent_types == [('shutdown', 55), ('shutdown', 56)]


@pytest.mark.asyncio
async def test_startup_notification_goes_to_each_supervisor_channel():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot._connection = SimpleNamespace(user=SimpleNamespace(name='Guardian bot'))
    bot._ready_event = asyncio.Event()
    bot.supervisor_channels = [55, 56]
    bot._startup_message_sent = False
    bot._ttl_cleanup_task = SimpleNamespace(done=lambda: False)
    bot.landing_to_be_confirmed = {}
    bot.msg_hello = 'Bot online'
    sent = []

    async def send_message(message, notification_type=None, channel_id=None):
        sent.append((message, notification_type, channel_id))

    bot.send_message_async = send_message

    await bot.on_ready()

    assert sent == [
        (bot.msg_hello, 'startup', 55),
        (bot.msg_hello, 'startup', 56),
    ]


@pytest.mark.asyncio
async def test_pilot_startup_message_explains_and_registers_problem_signal():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot._connection = SimpleNamespace(user=SimpleNamespace(name='Guardian bot'))
    bot._ready_event = asyncio.Event()
    bot.supervisor_channels = [55]
    bot.pilot_startup_prompts = [{
        'name': 'Pilot',
        'puretrack_key': 'X-pilot',
        'discord_user_id': 7,
        'discord_channel_id': 77,
        'supervisor_channel_id': 55,
        'supervisor_user_ids': {99},
    }]
    bot._startup_message_sent = False
    bot._ttl_cleanup_task = SimpleNamespace(done=lambda: False)
    bot.landing_to_be_confirmed = {}
    bot.msg_hello = "I'm connected. 🤓"
    bot.msg_pilot_hello = (
        "To report a problem at any time, react 👎 to this message. "
        "Your angel will be alerted.\n"
        "Stay safe."
    )
    sent = []

    async def send_message(message, notification_type=None, channel_id=None):
        sent.append((message, notification_type, channel_id))
        return 100 + len(sent)

    bot.send_message_async = send_message

    await bot.on_ready()

    assert sent == [
        (bot.msg_hello, 'startup', 55),
        (bot.msg_hello, 'startup', 77),
        (bot.msg_pilot_hello, None, 77),
    ]
    confirmation = bot.landing_to_be_confirmed[103]
    assert confirmation['notification_type'] == 'report_issue'
    assert confirmation['discord_id'] == 7
    assert confirmation['paraglider_key'] == 'X-pilot'
    assert confirmation['created_at'] is None
    assert set(bot.landing_to_be_confirmed) == {103}
    assert "I'm connected." not in bot.msg_pilot_hello


@pytest.mark.asyncio
async def test_supervisor_only_startup_prompt_uses_global_channel_and_authorizes_wife():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot._connection = SimpleNamespace(user=SimpleNamespace(name='Guardian bot'))
    bot._ready_event = asyncio.Event()
    bot.discord_channel_id = 55
    bot.supervisor_channels = [55]
    bot.pilot_startup_prompts = [{
        'name': 'Pilot',
        'puretrack_key': 'X-pilot',
        'discord_user_id': None,
        'discord_channel_id': None,
        'supervisor_channel_id': None,
        'supervisor_user_ids': {99},
    }]
    bot._startup_message_sent = False
    bot._ttl_cleanup_task = SimpleNamespace(done=lambda: False)
    bot.landing_to_be_confirmed = {}
    bot.msg_hello = "I'm connected. 🤓"
    bot.msg_pilot_hello = (
        "To report a problem at any time, react 👎 to this message. "
        "Your angel will be alerted.\n"
        "Stay safe."
    )
    sent = []

    async def send_message(message, notification_type=None, channel_id=None):
        sent.append((message, notification_type, channel_id))
        return 100 + len(sent)

    bot.send_message_async = send_message

    await bot.on_ready()

    assert sent[-2:] == [
        (bot.msg_hello, 'startup', 55),
        (bot.msg_pilot_hello, None, 55),
    ]
    confirmation = bot.landing_to_be_confirmed[103]
    assert confirmation['discord_id'] is None
    assert confirmation['supervisor_user_ids'] == {99}
    assert set(bot.landing_to_be_confirmed) == {103}
    assert bot._actor_role_for_confirmation(99, confirmation) == 'supervisor'


@pytest.mark.asyncio
async def test_pilot_can_report_problem_with_thumbs_down_on_startup_instructions():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot.discord_channel_id = 55
    bot.landing_to_be_confirmed = {
        100: {
            'discord_id': 7,
            'paraglider_key': 'X-pilot',
            'pilot_name': 'Pilot',
            'notification_type': 'report_issue',
            'supervisor_channel_id': 55,
            'channel_id': 77,
            'supervisor_user_ids': {99},
            'created_at': None,
            'message_ids': {100},
            'completed': False,
        },
    }
    bot._cleanup_expired_confirmations = lambda: None
    bot._pending_confirmation_events = asyncio.Queue()
    bot._positive_reaction_emojis = DiscordBot._POSITIVE_REACTION_EMOJIS
    bot._negative_reaction_emojis = DiscordBot._NEGATIVE_REACTION_EMOJIS
    bot.msg_negative_response = (
        "🚨 Your response indicates that you need assistance or are not safe.\n"
        "The alert remains active. The guardian has been notified.\n\n"
        "To update your response, reply to this message or react to it:\n"
        "👍 = I am safe and have landed; clear the alert.\n"
        "👎 = I still need assistance or am not safe."
    )
    sent = []

    async def post_message_to_channel(channel_id, message):
        sent.append((channel_id, message))
        return 200

    bot.post_message_to_channel = post_message_to_channel

    await bot._handle_reaction_confirmation(100, 7, '👎', 'Pilot', channel_id=77)

    event = await bot._pending_confirmation_events.get()
    assert event['type'] == 'assistance_requested'
    assert event['paraglider_key'] == 'X-pilot'
    assert 'reply to this message or react to it:' in sent[0][1]
    assert 100 in bot.landing_to_be_confirmed
    assert bot.landing_to_be_confirmed[200]['notification_type'] == 'alert'
    assert bot.landing_to_be_confirmed[200]['created_at'] is None


@pytest.mark.asyncio
async def test_assistance_notification_uses_red_embed():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot.discord_channel_id = 55
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
    bot.discord_channel_id = 55
    bot._send_max_retries = 2
    bot._send_base_backoff = 0
    bot.send_confirmation_dm = False
    bot.landing_to_be_confirmed = {}
    bot.msg_confirmation_instructions = (
        "To respond, reply to this message or react to it:\n"
        "👍 = I am safe and have landed.\n"
        "👎 = I need assistance or I am not safe."
    )
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

    async def post_bye(discord_id, actor_role="pilot"):
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
    bot.discord_channel_id = 55
    bot.msg_confirmation_instructions = (
        "To respond, reply to this message or react to it:\n"
        "👍 = I am safe and have landed.\n"
        "👎 = I need assistance or I am not safe."
    )
    bot.msg_unrecognized_response = (
        "⚠️ {mention}, response not recognized.\n"
        + bot.msg_confirmation_instructions
    )
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

    expected = (
        "⚠️ <@7>, response not recognized.\n"
        + bot.msg_confirmation_instructions
    )
    assert sent_messages == [(55, expected)]
    assert bot.landing_to_be_confirmed[100] is confirmation
    assert bot.landing_to_be_confirmed[101] is confirmation


@pytest.mark.asyncio
async def test_thumbs_down_rejects_confirmation_without_replying_bye():
    bot = DiscordBot.__new__(DiscordBot)
    bot._connection = SimpleNamespace(user=SimpleNamespace(id=42))
    bot.logger = get_logger('test')
    bot.discord_channel_id = 55
    bot.msg_negative_response = 'The alert remains active.'
    bot.landing_to_be_confirmed = {
        100: {'discord_id': 7, 'paraglider_key': 'X-pilot'},
    }
    bot._pending_confirmation_events = asyncio.Queue()
    bot._cleanup_expired_confirmations = lambda: None

    async def post_bye(discord_id, actor_role="pilot"):
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
    bot._cleanup_expired_confirmations = lambda: None
    bot._positive_reaction_emojis = DiscordBot._POSITIVE_REACTION_EMOJIS
    bot._negative_reaction_emojis = DiscordBot._NEGATIVE_REACTION_EMOJIS
    bot.discord_channel_id = 55
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
    bot.discord_channel_id = 55
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
async def test_active_alert_confirmation_survives_ttl_cleanup():
    bot = DiscordBot.__new__(DiscordBot)
    bot.logger = get_logger('test')
    bot._pending_confirmation_ttl = 1
    bot.discord_channel_id = 55
    bot.landing_to_be_confirmed = {}
    bot.msg_confirmation_instructions = (
        "To respond, reply to this message or react to it:\n"
        "👍 = I am safe and have landed.\n"
        "👎 = I need assistance or I am not safe."
    )
    bot._ready_event = asyncio.Event()
    bot._ready_event.set()
    bot.is_ready = lambda: True

    async def post_message_to_channel(channel_id, message, embed=None):
        return 100 if embed is not None else 101

    bot.post_message_to_channel = post_message_to_channel
    await bot.post_waiting_landing_confirmation(
        7,
        'Alert for Pilot',
        'X-pilot',
        notification_type='alert',
    )

    confirmation = bot.landing_to_be_confirmed[100]
    assert confirmation['persistent'] is True
    assert bot.landing_to_be_confirmed[101] is confirmation
    confirmation['created_at'] = asyncio.get_running_loop().time() - 10

    bot._cleanup_expired_confirmations()

    assert set(bot.landing_to_be_confirmed) == {100, 101}


def test_clearing_alert_removes_its_confirmation_messages_only():
    bot = DiscordBot.__new__(DiscordBot)
    bot.landing_to_be_confirmed = {}
    alert_confirmation = {
        'paraglider_key': 'X-pilot',
        'notification_type': 'alert',
        'message_ids': {100, 101},
        'completed': False,
    }
    other_confirmation = {
        'paraglider_key': 'X-other',
        'notification_type': 'alert',
        'message_ids': {200},
        'completed': False,
    }
    bot.landing_to_be_confirmed.update({
        100: alert_confirmation,
        101: alert_confirmation,
        200: other_confirmation,
    })

    bot.clear_pending_alert_confirmations('X-pilot')

    assert bot.landing_to_be_confirmed == {200: other_confirmation}
    assert alert_confirmation['completed'] is True
    assert alert_confirmation['message_ids'] == set()
    assert other_confirmation['completed'] is False


@pytest.mark.asyncio
async def test_two_pending_confirmations_both_get_bye_on_thumbs_up():
    """First ack must not wipe the second pilot's pending confirmation."""
    bot = DiscordBot.__new__(DiscordBot)
    bot._connection = SimpleNamespace(user=SimpleNamespace(id=42))
    bot.logger = get_logger('test')
    bot.discord_channel_id = 55
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

    async def post_bye(discord_id, actor_role="pilot"):
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

    async def post_bye(discord_id, actor_role="pilot"):
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


@pytest.mark.asyncio
async def test_group_supervisor_reaction_confirms_landing():
    bot = DiscordBot.__new__(DiscordBot)
    bot._connection = SimpleNamespace(user=SimpleNamespace(id=42))
    bot.logger = get_logger('test')
    bot.landing_to_be_confirmed = {
        100: {
            'discord_id': 7,
            'paraglider_key': 'X-pilot',
            'supervisor_user_ids': {99},
            'created_at': asyncio.get_running_loop().time(),
            'message_ids': {100},
        },
    }
    bot._pending_confirmation_events = asyncio.Queue()
    bot._cleanup_expired_confirmations = lambda: None
    byes = []

    async def post_bye(discord_id, actor_role='pilot'):
        byes.append((discord_id, actor_role))

    bot.post_bye = post_bye

    await bot.on_raw_reaction_add(SimpleNamespace(
        user_id=99,
        message_id=100,
        emoji='👍',
    ))

    event = await bot._pending_confirmation_events.get()
    assert event['type'] == 'landing_confirmed'
    assert event['discord_id'] == 99
    assert event['actor_role'] == 'supervisor'
    assert event['paraglider_key'] == 'X-pilot'
    assert byes == [(99, 'supervisor')]
    assert bot.landing_to_be_confirmed == {}


@pytest.mark.asyncio
async def test_group_supervisor_can_reject_confirmation_without_pilot_discord_id():
    bot = DiscordBot.__new__(DiscordBot)
    bot._connection = SimpleNamespace(user=SimpleNamespace(id=42))
    bot.logger = get_logger('test')
    bot.landing_to_be_confirmed = {
        100: {
            'discord_id': None,
            'paraglider_key': 'X-orphan',
            'supervisor_user_ids': {99},
            'created_at': asyncio.get_running_loop().time(),
            'message_ids': {100},
        },
    }
    bot._pending_confirmation_events = asyncio.Queue()
    bot._cleanup_expired_confirmations = lambda: None
    negatives = []

    async def post_negative_acknowledgment(discord_id):
        negatives.append(discord_id)

    bot.post_negative_acknowledgment = post_negative_acknowledgment

    await bot.on_raw_reaction_add(SimpleNamespace(
        user_id=99,
        message_id=100,
        emoji='👎',
    ))

    event = await bot._pending_confirmation_events.get()
    assert event['type'] == 'landing_rejected'
    assert event['actor_role'] == 'supervisor'
    assert event['paraglider_key'] == 'X-orphan'
    assert negatives == [99]


@pytest.mark.asyncio
async def test_third_party_reaction_is_not_addressed():
    bot = DiscordBot.__new__(DiscordBot)
    bot._connection = SimpleNamespace(user=SimpleNamespace(id=42))
    bot.logger = get_logger('test')
    bot.landing_to_be_confirmed = {
        100: {
            'discord_id': 7,
            'paraglider_key': 'X-pilot',
            'supervisor_user_ids': set(),
            'created_at': asyncio.get_running_loop().time(),
            'message_ids': {100},
        },
    }
    bot._pending_confirmation_events = asyncio.Queue()
    bot._cleanup_expired_confirmations = lambda: None
    not_addressed = []

    async def post_not_addressed(discord_id):
        not_addressed.append(discord_id)

    bot.post_not_addressed = post_not_addressed

    await bot.on_raw_reaction_add(SimpleNamespace(
        user_id=99,
        message_id=100,
        emoji='👍',
    ))

    assert bot._pending_confirmation_events.empty()
    assert not_addressed == [99]
    assert 100 in bot.landing_to_be_confirmed


@pytest.mark.asyncio
async def test_pilot_reply_is_accepted_with_group_supervisors_configured():
    bot = DiscordBot.__new__(DiscordBot)
    bot_user = SimpleNamespace(id=42)
    bot._connection = SimpleNamespace(user=bot_user)
    bot.logger = get_logger('test')
    bot.landing_to_be_confirmed = {
        100: {
            'discord_id': 7,
            'paraglider_key': 'X-pilot',
            'supervisor_user_ids': {99},
        },
    }
    bot._pending_confirmation_events = asyncio.Queue()
    bot._cleanup_expired_confirmations = lambda: None
    byes = []

    async def post_bye(discord_id, actor_role='pilot'):
        byes.append((discord_id, actor_role))

    async def process_commands(message):
        return None

    bot.post_bye = post_bye
    bot.process_commands = process_commands

    await bot.on_message(SimpleNamespace(
        author=SimpleNamespace(id=7, name='Pilot'),
        content='yes',
        reference=SimpleNamespace(
            resolved=SimpleNamespace(id=100, author=bot_user),
        ),
    ))

    event = await bot._pending_confirmation_events.get()
    assert event['type'] == 'landing_confirmed'
    assert event['actor_role'] == 'pilot'
    assert byes == [(7, 'pilot')]


def test_supervisor_channels_loaded_from_config():
    bot = DiscordBot({
        'supervisor_channels': ['1', 2, 0],
    })
    assert bot.supervisor_channels == [1, 2]


def test_bot_confirmation_instructions_use_explicit_targets_and_choices():
    bot = DiscordBot({})

    assert bot.msg_hello == "I'm connected. 🤓"
    assert 'react 👎 to this message' in bot.msg_pilot_hello
    assert 'To respond, reply to this message or react to it:' in (
        bot.msg_confirmation_instructions
    )
    assert '👍 = I am safe and have landed.' in bot.msg_confirmation_instructions
    assert '👎 = I need assistance or I am not safe.' in bot.msg_confirmation_instructions
    assert 'reply to this message or react to it:' in bot.msg_negative_response
    assert '👍 = I am safe and have landed; clear the alert.' in (
        bot.msg_negative_response
    )


@pytest.mark.asyncio
async def test_group_supervisor_text_reply_confirms_landing():
    bot = DiscordBot.__new__(DiscordBot)
    bot_user = SimpleNamespace(id=42)
    bot._connection = SimpleNamespace(user=bot_user)
    bot.logger = get_logger('test')
    bot.landing_to_be_confirmed = {
        100: {
            'discord_id': 7,
            'paraglider_key': 'X-pilot',
            'supervisor_user_ids': {99},
        },
    }
    bot._pending_confirmation_events = asyncio.Queue()
    bot._cleanup_expired_confirmations = lambda: None
    byes = []

    async def post_bye(discord_id, actor_role='pilot'):
        byes.append((discord_id, actor_role))

    async def process_commands(message):
        return None

    bot.post_bye = post_bye
    bot.process_commands = process_commands

    await bot.on_message(SimpleNamespace(
        author=SimpleNamespace(id=99, name='Guardian'),
        content='I am safe',
        reference=SimpleNamespace(
            resolved=SimpleNamespace(id=100, author=bot_user),
        ),
    ))

    event = await bot._pending_confirmation_events.get()
    assert event['type'] == 'landing_confirmed'
    assert event['actor_role'] == 'supervisor'
    assert byes == [(99, 'supervisor')]
