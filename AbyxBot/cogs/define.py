from __future__ import annotations
# stdlib
import json
from urllib.parse import quote as urlquote
from typing import TYPE_CHECKING, TypedDict, Literal, AsyncIterable, Iterable, \
    Any, get_args
from typing_extensions import assert_never, NotRequired

# 3rd-party
import discord
from discord import app_commands

# 1st-party
from ..i18n import error_embed, Msg, mkembed, mkmsg
from .words import fetch_words, WordResp
if TYPE_CHECKING:
    from ..lib.client import AbyxBot

Dictionary = Literal[
    'wiktionary',
    'datamuse',
]

# helper function for reading big lines from a stream

async def chunks_to_lines(chunks: AsyncIterable[bytes]) -> AsyncIterable[bytes]:
    # convoluted buffered line reading to deal with some lines
    # being too long for stream.__anext__()
    buffer = bytearray()
    async for chunk in chunks:
        first_piece, *pieces = chunk.split(b'\n')
        buffer.extend(first_piece)
        if pieces:
            yield bytes(buffer)
            *pieces, last_piece = pieces
            buffer[:] = last_piece
            for piece in pieces:
                yield piece
    if buffer: # check for last line
        yield bytes(buffer)

# helper to ellipsize overlong field values and replace overlong embeds

def trunc_embeds(
    ctx: discord.Interaction,
    error_message: Any,
    embeds: Iterable[discord.Embed],
) -> Iterable[discord.Embed]:
    embeds = map(
        lambda e: e if len(e) <= 6000
        else error_embed(ctx, error_message),
        embeds
    )
    for embed in embeds:
        for j, field in enumerate(embed.fields):
            if field.value is None:
                continue
            if len(field.value) > 1024:
                embed.set_field_at(
                    j, name=field.name,
                    value=field.value[:1021] + '...',
                    inline=field.inline
                )
        yield embed

# NOTE: These TypedDicts only include fields we use

class KaikkiSense(TypedDict, total=False): # raw_glosses may be unset
    raw_glosses: list[str]
    glosses: list[str] # substitutes for raw_glosses when it is not set

class KaikkiSound(TypedDict, total=False): # any of these may be unset
    text: str
    mp3_url: str
    ogg_url: str
    ipa: str
    enpr: str
    tags: list[str]

class KaikkiDefinition(TypedDict):
    etymology_text: str
    pos: str # part of speech, not position
    senses: list[KaikkiSense]
    sounds: NotRequired[list[KaikkiSound]]
    word: str

async def wiktionary(ctx: discord.Interaction[AbyxBot], word: str):
    """Wiktionary definition of a word/phrase."""
    KAIKKI_URL = 'https://kaikki.org/dictionary/English/meaning/{}/{}/{}.jsonl'
    COMMA = mkmsg(ctx, ',')
    defns: list[KaikkiDefinition] = []
    async with ctx.client.session.get(KAIKKI_URL.format(word[:1], word[:2], word)) as resp:
        if resp.ok:
            async for line in chunks_to_lines(resp.content.iter_any()):
                defns.append(json.loads(line))
    if not defns:
        await ctx.edit_original_response(
            embed=error_embed(ctx, Msg('words/no-def', word)))
        return
    embeds: list[discord.Embed] = []
    for i, defn in enumerate(defns, start=1):
        # construct sounds field
        sounds: list[str] = []
        for sound in defn.get('sounds', []):
            chunk = ''
            # text pronunciation
            if 'ipa' in sound:
                chunk = sound['ipa']
            elif 'enpr' in sound:
                chunk = sound['enpr']
            if 'tags' in sound and sound['tags']:
                tags = '(%s)' % COMMA.join(sound['tags'])
                chunk = tags + ' ' + chunk
            # audio recording
            if 'mp3_url' in sound and 'text' in sound:
                chunk = '[{text}]({mp3_url})'.format(**sound)
            elif 'ogg_url' in sound and 'text' in sound:
                chunk = '[{text}]({ogg_url})'.format(**sound)
            # only add if any useful sound present
            if chunk:
                sounds.append(chunk)
        # construct glosses field
        all_glosses: list[list[str]] = [[
            f'{j}. {gloss}'
            for j, gloss in enumerate(
                # raw_glosses is omitted when identical to glosses
                sense.get('raw_glosses', sense.get('glosses', [])),
                start=1
            )
        ] for sense in defn['senses']]
        if all(len(glosses) == 1 for glosses in all_glosses):
            all_glosses = [[glosses[0] for glosses in all_glosses]]

        # construct total embed
        embeds.append(mkembed(
            ctx, title=Msg('define/defn-title', defn['word'], i),
            url='https://en.wiktionary.org/wiki/' + urlquote(defn['word']),
            fields=(
                (Msg('define/pos'), defn['pos'], True),
                (Msg('define/sound'), COMMA.join(sounds), True),
                *(
                    (Msg('define/glosses', j), '\n'.join(glosses), False)
                    for j, glosses in enumerate(all_glosses, start=1)
                ),
            ),
            footer=Msg('define/src-kaikki'),
            color=0xfffffe,
        ))
    await ctx.edit_original_response(embeds=list(trunc_embeds(
        ctx, Msg('define/embed-too-long-kaikki', urlquote(word)), embeds)))

async def datamuse(ctx: discord.Interaction[AbyxBot], word: str):
    """Datamuse definition of a word/phrase."""
    results = await fetch_words(ctx, qe='sp', sp=word, md='dpsrf', ipa='1', max=1)
    result: WordResp = results[0]
    if 'defs' not in result:
        await ctx.edit_original_response(
            embed=error_embed(ctx, Msg('words/no-def', word)))
        return
    tags: list[str] = result['tags']
    parts_of_speech = set()
    pron: str = '(?)'
    freq: str = '(?)'
    for tag in tags:
        if tag.startswith('ipa_pron:'):
            pron = tag.split(':', 1)[1]
        elif tag.startswith('f:'):
            freq = tag.split(':', 1)[1]
        elif tag != 'query' and ':' not in tag:
            parts_of_speech.add(tag)
    syllables: int = result['numSyllables']
    defs: list[str] = result['defs']
    root_word: str = result.get('defHeadword', word)
    embed = mkembed(ctx,
        title=Msg('words/word-info', word),
        description=Msg('words/word-root', root_word),
        fields=(
            (Msg('words/word-pronunciation'), pron, True),
            (Msg('words/word-syllables'), str(syllables), True),
            (Msg('words/word-parts-of-speech'),
             mkmsg(ctx, ',').join(parts_of_speech),
             True),
            (Msg('words/word-frequency'), str(freq), True),
            (Msg('words/word-definitions'), '\n'.join(
                f'{i}. ' + defn.replace('\t', '\N{NO-BREAK SPACE}' * 4)
                for i, defn in enumerate(defs, start=1)
            ), False)
        ),
        footer=Msg('define/src-datamuse'),
        color=0xfffffe,
    )
    await ctx.edit_original_response(embeds=list(trunc_embeds(
        ctx, Msg('define/embed-too-long-datamuse', urlquote(word)), [embed]
    )))

@app_commands.command()
@app_commands.describe(word='A word (or sometimes phrase).')
@app_commands.choices(dictionary=[
    app_commands.Choice(name=app_commands.locale_str(
        dictionary, key=f'define/dict-{dictionary}'
    ), value=dictionary)
    for dictionary in get_args(Dictionary)
])
async def define(ctx: discord.Interaction[AbyxBot], word: str,
                 dictionary: Dictionary = 'wiktionary'):
    """Various information about a word, including its definition(s)."""
    await ctx.response.defer()
    if dictionary == 'wiktionary':
        await wiktionary(ctx, word)
    elif dictionary == 'datamuse':
        await datamuse(ctx, word)
    else:
        assert_never(dictionary)

def setup(bot: AbyxBot):
    bot.tree.add_command(define)
