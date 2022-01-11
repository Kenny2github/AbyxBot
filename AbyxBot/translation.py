# stdlib
import json
import os
import re
from typing import Callable, Union
from functools import partial
import asyncio

# 3rd-party
import discord
from google.cloud import translate
from discord.ext.slash import Option, SlashBot

# 1st-party
from .chars import REGU
from .config import config
from .discord_markdown import html_to_md, md_to_html
from .logger import get_logger
from .i18n import Context, IDContext, Msg
from .utils import AttrDict, asyncify

logger = get_logger('translation')

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
    client.get_supported_languages(parent=PARENT).languages]
logger.info('Loaded supported translation languages')

async def translate_text(text: Union[str, list[str]],
                         dest: str, source: str = None) -> list[AttrDict]:
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
                           dest: str, source: str = None, link: str = None):
    """Send the translation to the appropriate context."""
    results = await translate_text(text, dest, source)
    # assume the text is all in the same language *shrug*
    source = results[0].lang
    if dest == source:
        # can't use ctx.embed because ctx may not be a Context
        asyncio.create_task(method(embed=discord.Embed(
            title=str(Msg('error', lang=ctx)),
            description=str(Msg('translation/same-lang', lang=ctx)),
            color=discord.Color.red()
        )))
        return
    result_text = '\n\n'.join(t.text for t in results)
    embed = discord.Embed(
        description=result_text,
        color=0x36393f
    ).set_footer(
        text=str(Msg(
            'translation/requested-by',
            ctx.author if isinstance(ctx, Context) else ctx, lang=ctx))
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

async def translate(
    ctx: Context,
    to_language: Option('The language code to translate to.') = None,
    from_language: Option('The language code to translate from.') = None,
    count: Option('Number of messages into the past to translate.',
                  min_value=1) = 1,
    text: Option('Text to translate.') = None
):
    """Translate message text. Run `/help translate`."""
    await ctx.respond(deferred=True)
    if to_language is None:
        to_language = Msg.get_lang(ctx)
    if text:
        text = [text]
        url = None
    else:
        msgs: list[discord.Message] = (await ctx.channel.history(
            limit=count).flatten())[::-1]
        url = msgs[0].jump_url
        text = [m.content for m in msgs]
    await send_translation(ctx, ctx.respond, text, to_language, from_language, url)

def setup(bot: SlashBot):
    async def on_raw_reaction_add(event: discord.RawReactionActionEvent):
        emoji: str = event.emoji.name
        if not (
            len(emoji) == 2
            and emoji[0] in LETTERS
            and emoji[1] in LETTERS
        ):
            return # not a flag, ignore
        country_code = LETTERS[emoji[0]] + LETTERS[emoji[1]]
        lang: str = ''
        for country_lang in COUNTRYLANGS[country_code]:
            if country_lang in LANGUAGES:
                lang = country_lang
                break
            country_lang = country_lang.split('-')[0] # try only the first part
            if country_lang in LANGUAGES:
                lang = country_lang
                break
        else:
            logger.warning('No supported language for %s', country_code)
            return # no supported language, ignore
        user: discord.User = bot.get_user(event.user_id) # for i18n context
        # needed to fetch the message in question
        channel: discord.TextChannel = bot.get_channel(event.channel_id)
        message: discord.Message = await channel.fetch_message(event.message_id)
        method = partial(message.reply, mention_author=False) # don't ping
        logger.info(
            'User %s\t(%18d) in channel %s\t(%18d) '
            'translating message %18d to %s (from %s)',
            user, user.id, channel, channel.id, message.id, lang, country_code)
        await send_translation(user, method, [message.content], lang)
    bot.event(on_raw_reaction_add)
    bot.add_slash(translate)
