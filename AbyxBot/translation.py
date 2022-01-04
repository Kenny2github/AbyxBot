import re
from typing import Callable, Union
import asyncio
import discord
from google.cloud import translate
from discord.ext.slash import Option, SlashBot, cmd
from .config import config
from .discord_markdown import html_to_md, md_to_html
from .i18n import Context, IDContext, Msg
from .utils import AttrDict

client: translate.TranslationServiceClient = \
    translate.TranslationServiceClient \
    .from_service_account_json(config.gcloud_auth_json)
PARENT = f'projects/{config.gcloud_project_id}/locations/global'
ESCAPES = re.compile('(<[:@#][^>]+>|:[^:]+:)')
UNK = r'<unk value="\1" />'

async def translate_text(text: Union[str, list[str]],
                         dest: str, source: str = None) -> list[AttrDict]:
    """Translate text, preserving Discord formatting."""
    if isinstance(text, str):
        text = [text]
    text = [ESCAPES.sub(UNK, md_to_html(chunk)) for chunk in text]
    req = {
        'parent': PARENT,
        'mime_type': 'text/html',
        'target_language_code': dest,
        'contents': text
    }
    if source:
        req['source_language_code'] = source
    resp = await asyncio.get_event_loop().run_in_executor(
        None, client.translate_text, req)
    return [AttrDict({
        'text': re.sub(UNK.replace(r'\1', '([^"]+)'), r'\1',
                       html_to_md(t.translated_text)),
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
    bot.add_slash(translate)