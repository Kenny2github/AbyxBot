# stdlib
import json
import os
import re
from logging import getLogger
from typing import Callable, Optional, Union
from functools import partial
import asyncio

# 3rd-party
import discord
from discord import app_commands
from discord.ext import commands
from google.cloud import translate

# 1st-party
from .chars import REGU
from .config import config
from .discord_markdown import html_to_md, md_to_html
from .i18n import IDContext, Msg, error_embed
from .type_hints import HistoriedChannel
from .utils import AttrDict, asyncify

logger = getLogger(__name__)

client: translate.TranslationServiceClient = \
    translate.TranslationServiceClient \
    .from_service_account_json(config.gcloud_auth_json)
PARENT = f'projects/{config.gcloud_project_id}/locations/global'
ESCAPES = re.compile('(<[:@#][^>]+>|:[^:]+:)')
UNK = r'<unk value="\1" />'
LETTERS = {reg: letter for letter, reg in REGU.items()}
with open(os.path.join('AbyxBot', 'countrylangs.json')) as f:
    COUNTRYLANGS: dict[str, list[str]] = json.load(f)
LANGUAGES: list[str] = [
    language.language_code for language in
    client.get_supported_languages(parent=PARENT).languages] # type: ignore
SPECIAL_LANGS = {
    '\N{WAVING BLACK FLAG}'
    + ''.join(chr(0xe0000 + ord(c)) for c in code)
    + '\N{CANCEL TAG}'
    : (code, langcode)
    for code, langcode in {
        'gbwls': 'cy', 'gbsct': 'gd', 'gbeng': 'en'}.items()
}
logger.info('Loaded supported translation languages')

async def translate_text(text: Union[str, list[str]],
                         dest: str, source: Optional[str] = None
                         ) -> list[AttrDict]:
    """Translate text, preserving Discord formatting."""
    if isinstance(text, str):
        text = [text]
    text = [ESCAPES.sub(UNK, md_to_html(chunk)) for chunk in text]
    logger.debug('Translating from %s to %s:\n%s', source, dest, text)
    req = {
        'parent': PARENT,
        'mime_type': 'text/html',
        'target_language_code': dest,
        'contents': text
    }
    if source:
        req['source_language_code'] = source
    resp = await asyncify(client.translate_text, req)
    return [AttrDict({
        'text': html_to_md(re.sub(
            UNK.replace(r'\1', '([^"]+)'),
            r'\1', t.translated_text)),
        'lang': t.detected_language_code or source})
    for t in resp.translations]

async def send_translation(ctx: IDContext, method: Callable, text: list[str],
                           dest: str, source: Optional[str] = None,
                           link: Optional[str] = None):
    """Send the translation to the appropriate context."""
    results = await translate_text(text, dest, source)
    # assume the text is all in the same language *shrug*
    source = results[0].lang
    if dest == source:
        asyncio.create_task(method(embed=error_embed(
            ctx, Msg('translation/same-lang', lang=ctx)
        )))
        return
    result_text = '\n\n'.join(t.text for t in results)
    embed = discord.Embed(
        description=result_text,
        color=0x36393f
    ).set_footer(
        text=str(Msg(
            'translation/requested-by',
            ctx.user if isinstance(ctx, discord.Interaction)
            else ctx, lang=ctx))
    )
    if link is not None:
        embed.set_author(
            name=str(Msg('translation/origin', source, dest, lang=ctx)),
            url=link
        )
    else: # link None means we're replying, possibly to the command invocation
        embed.set_author(
            name=str(Msg('translation/origin', source, dest, lang=ctx))
        )
    asyncio.create_task(method(embed=embed))

@app_commands.command(name='translate')
@app_commands.describe(
    to_language='The language code to translate to.',
    from_language='The language code to translate from.',
    count='Number of messages into the past to translate.',
    text='Text to translate.',
)
async def translate_command(
    ctx: discord.Interaction,
    to_language: Optional[str] = None,
    from_language: Optional[str] = None,
    count: app_commands.Range[int, 1] = 1,
    text: Optional[str] = None
):
    """Translate message text. Run `/help translate`."""
    if to_language is None:
        to_language = Msg.get_lang(ctx)
    if text:
        await ctx.response.defer()
        texts = [text]
        url = None
    elif isinstance(ctx.channel, HistoriedChannel):
        await ctx.response.defer()
        msgs: list[discord.Message] = [m async for m in ctx.channel.history(
            limit=count+1)][:0:-1]
        url = msgs[0].jump_url
        texts = [m.content for m in msgs]
    else:
        await ctx.response.send_message(
            '\N{EXCLAMATION QUESTION MARK}', ephemeral=True)
        raise RuntimeError('Slash command run in non-textable channel')
    await send_translation(ctx, ctx.edit_original_message, texts,
                           to_language, from_language, url)

@app_commands.context_menu(name='Translate')
async def translate_context_menu(
    ctx: discord.Interaction, msg: discord.Message
):
    """Translate the message to your configured language (English if unset)."""
    lang = Msg.get_lang(ctx)
    texts = [msg.content]
    url = msg.jump_url
    await send_translation(ctx, ctx.response.send_message,
                           texts, lang, None, url)

def setup(bot: commands.Bot):
    bot.tree.add_command(translate_command)
    bot.tree.add_command(translate_context_menu)
    @bot.listen()
    async def on_raw_reaction_add(event: discord.RawReactionActionEvent):
        emoji: str = str(event.emoji)
        country_code, lang = SPECIAL_LANGS.get(emoji, ('', ''))
        if not lang:
            if not (
                len(emoji) == 2
                and emoji[0] in LETTERS
                and emoji[1] in LETTERS
            ):
                return # not a flag, ignore
            country_code = LETTERS[emoji[0]] + LETTERS[emoji[1]]
            for country_lang in COUNTRYLANGS[country_code]:
                if country_lang in LANGUAGES:
                    lang = country_lang
                    break
                # try only the en of en-GB, for example
                country_lang = country_lang.split('-')[0]
                if country_lang in LANGUAGES:
                    lang = country_lang
                    break
            else:
                logger.warning('No supported language for %s', country_code)
                return # no supported language, ignore
        user = bot.get_user(event.user_id) # for i18n context
        if user is None:
            return # can't find user, ignore event
        # needed to fetch the message in question
        channel = bot.get_channel(event.channel_id)
        if not isinstance(channel, HistoriedChannel):
            return # ditto
        message: discord.Message = await channel.fetch_message(event.message_id)
        for reaction in message.reactions:
            if str(reaction) == emoji and reaction.count > 1:
                logger.debug(
                    'Ignoring duplicate request for translation to %s', lang)
                return
        method = partial(message.reply, mention_author=False) # don't ping
        logger.info(
            'User %s\t(%18d) in channel %s\t(%18d) '
            'translating message %18d to %s (from %s)',
            user, user.id, channel, channel.id, message.id, lang, country_code)
        await send_translation(user, method, [message.content], lang)
