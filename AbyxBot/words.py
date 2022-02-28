# stdlib
from functools import wraps
from typing import TypedDict
from operator import itemgetter
from itertools import groupby

# 3rd-party
import aiohttp
import discord
from discord.ext.slash import Group, Option, SlashBot, cmd, group

# 1st-party
from .i18n import Context, Msg

# TODO: implement censoring

session: aiohttp.ClientSession = None

TITLES = {
    'ml': 'words/meaning-title',
    'sl': 'words/sounding-like-title',
    'sp': 'words/spelled-like-title',
    'rel_jja': 'words/modified-by-title',
    'rel_jjb': 'words/modifying-title',
    'rel_syn': 'words/synonyms-title',
    'rel_trg': 'words/associated-with-title',
    'rel_ant': 'words/antonyms-title',
    'rel_spc': 'words/hypernyms-title',
    'rel_gen': 'words/hyponyms-title',
    'rel_com': 'words/holonyms-title',
    'rel_par': 'words/meronyms-title',
    'rel_bga': 'words/after-title',
    'rel_bgb': 'words/before-title',
    'rel_hom': 'words/homophones-title',
    'rel_cns': 'words/consonant-match-title',
}

class WordResp(TypedDict):
    score: int
    word: str

async def fetch_words(**kwargs) -> list[WordResp]:
    """Get API data, passing kwargs."""
    API_URL = 'https://api.datamuse.com/words'
    async with session.get(API_URL, params=kwargs) as resp:
        return await resp.json()

def format_words(ctx: Context, api_code: str, word: str,
                 data: list[WordResp]) -> discord.Embed:
    """Format API data into an embed."""
    return ctx.embed(
        title=Msg(TITLES[api_code], word),
        description=ctx.msg(',').join(
            '{score}: {word}'.format(**i)
            for i in data
        ) or Msg('none-paren'),
        color=discord.Color.blue()
    )

def endpoint(group: Group, api_code: str):
    """Take a stub function and make it into a subcommand
    that returns the corresponding API data.
    """
    def decorator(func):
        @group.slash_cmd()
        @wraps(func)
        async def subcommand(ctx: Context, word: str):
            await ctx.respond(deferred=True)
            resp = await fetch_words(**{api_code: word})
            await ctx.respond(embed=format_words(ctx, api_code, word, resp))
        return subcommand
    return decorator

word_opt = Option('A word.')
of_opt = Option('A word.', name='of')

### /words <command> <arg>:<thing>

@group()
async def words(ctx: Context):
    """Lexical data related to words!"""

### rhyming is a special case

@words.slash_cmd()
async def rhyming(ctx: Context, word: Option(
    name='with', description='The word that other words rhyme with.'
)):
    """Words that rhyme with a word."""
    await ctx.respond(deferred=True)
    perf: list[WordResp] = await fetch_words(rel_rhy=word, md='s')
    near: list[WordResp] = await fetch_words(rel_nry=word, md='s')
    key = itemgetter('numSyllables')
    perf.sort(key=key)
    near.sort(key=key)
    comma = ctx.msg(',')
    fields = []
    for count, results in groupby(perf, key):
        fields.append((
            Msg('words/syllable-count', count),
            comma.join(result['word'] for result in results),
            False
        ))
    perf_embed = ctx.embed(
        Msg('words/perfect-rhymes'),
        # no description if any rhymes were found
        description=None if fields else Msg('none-paren'),
        fields=fields,
        color=0x55acee
    )
    fields = []
    for count, results in groupby(near, key):
        fields.append((
            Msg('words/syllable-count', count),
            comma.join(result['word'] for result in results),
            False
        ))
    near_embed = ctx.embed(
        Msg('words/near-rhymes'),
        # no description if any rhymes were found
        description=None if fields else Msg('none-paren'),
        fields=fields,
        color=0xe67e22
    )
    await ctx.respond(embeds=[perf_embed, near_embed])

@endpoint(words, 'ml')
async def meaning(ctx: Context, word: Option('A phrase.', name='phrase')):
    """Words that mean something."""

@endpoint(words, 'sl')
async def sounding(ctx: Context, word: Option('The sound.', name='like')):
    """Words that sound like something."""

@endpoint(words, 'sp')
async def spelled(ctx: Context, word: Option(
    'The spelling. Wildcards allowed - use `re*ing` to get words starting '
    'with re- and ending with -ing', name='like'
)):
    """Words that are spelled like something."""

@endpoint(words, 'rel_jja')
async def modified(ctx: Context, word: Option('An adjective.', name='by')):
    """Popular nouns modified by the given adjective, \
per Google Books Ngrams."""

@endpoint(words, 'rel_jjb')
async def modifying(ctx: Context, word: Option('A noun.')):
    """Popular adjectives used to modify the given noun, \
per Google Books Ngrams."""

@endpoint(words, 'rel_trg')
async def associated(ctx: Context, word: Option(
    name='with', description='A word.'
)):
    """Words that are statistically associated with the query word \
in the same piece of text."""

@endpoint(words, 'rel_bga')
async def after(ctx: Context, word: word_opt):
    """Frequent predecessors of the given word (per Google Books Ngrams)."""

@endpoint(words, 'rel_bgb')
async def before(ctx: Context, word: word_opt):
    """Words that frequently follow the given word \
(per Google Books Ngrams)."""

### /lex <command> <arg>:<word>

@group()
async def lex(ctx: Context):
    """Lexical data related to words!"""

@endpoint(lex, 'rel_syn')
async def synonyms(ctx: Context, word: of_opt):
    """Synonyms of the given word (per WordNet)."""

@endpoint(lex, 'rel_ant')
async def antonyms(ctx: Context, word: of_opt):
    """Antonyms of the given word (per WordNet)."""

@endpoint(lex, 'rel_spc')
async def hypernyms(ctx: Context, word: of_opt):
    """Hypernyms (words that are more general than the word, per WordNet)."""

@endpoint(lex, 'rel_gen')
async def hyponyms(ctx: Context, word: of_opt):
    """Hyponyms (words that are more specific than the word, per WordNet)."""

@endpoint(lex, 'rel_com')
async def holonyms(ctx: Context, word: of_opt):
    """Holonyms (words that are a part of the word, per WordNet)."""

@endpoint(lex, 'rel_par')
async def meronyms(ctx: Context, word: of_opt):
    """Meronyms (words that the word is part of, per WordNet)."""

@endpoint(lex, 'rel_hom')
async def homophones(ctx: Context, word: of_opt):
    """Homophones (words that sound alike)."""

@endpoint(lex, 'rel_cns')
async def homoconsonants(ctx: Context, word: of_opt):
    """Words that match consonants."""

### /define word:<word>

@cmd()
async def define(ctx: Context, word: Option('A word (or sometimes phrase).')):
    """Various information about a word, including its definition(s)."""
    await ctx.respond(deferred=True)
    result = await fetch_words(qe='sp', sp=word, md='dpsrf', ipa='1', max=1)
    result: WordResp = result[0]
    if 'defs' not in result:
        await ctx.respond(embed=ctx.error_embed(Msg('words/no-def', word)))
        return
    tags: list[str] = result['tags']
    parts_of_speech = set()
    pron: str = None
    freq: str = None
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
    await ctx.respond(embed=ctx.embed(
        title=Msg('words/word-info', word),
        description=Msg('words/word-root', root_word),
        fields=(
            (Msg('words/word-pronunciation'), pron, True),
            (Msg('words/word-syllables'), str(syllables), True),
            (Msg('words/word-parts-of-speech'),
             ctx.msg(',').join(parts_of_speech),
             True),
            (Msg('words/word-frequency'), str(freq), True),
            (Msg('words/word-definitions'), '\n'.join(
                f'{i}. ' + defn.replace('\t', '\N{NO-BREAK SPACE}' * 4)
                for i, defn in enumerate(defs, start=1)
            ), False)
        ),
        color=0xfffffe
    ))

def setup(bot: SlashBot):
    global session
    session = aiohttp.ClientSession()
    bot.slash.update({words, lex, define})
