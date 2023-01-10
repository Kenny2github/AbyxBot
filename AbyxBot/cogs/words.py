# stdlib
from functools import wraps
from typing import Callable, TypedDict
from operator import itemgetter
from itertools import groupby

# 3rd-party
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

# 1st-party
from ..i18n import Msg, mkembed, mkmsg, error_embed

# TODO: implement censoring

session: aiohttp.ClientSession = None # type: ignore - set on init

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
    tags: list[str]
    numSyllables: int
    defs: list[str]
    defHeadword: str

async def fetch_words(**kwargs) -> list[WordResp]:
    """Get API data, passing kwargs."""
    API_URL = 'https://api.datamuse.com/words'
    async with session.get(API_URL, params=kwargs) as resp:
        return await resp.json()

def format_words(ctx: discord.Interaction, api_code: str, word: str,
                 data: list[WordResp]) -> discord.Embed:
    """Format API data into an embed."""
    return mkembed(ctx,
        title=Msg(TITLES[api_code], word),
        description=mkmsg(ctx, ',').join(
            '{score}: {word}'.format(**i)
            for i in data
        ) or Msg('none-paren'),
        color=discord.Color.blue()
    )

def endpoint(group: app_commands.Group, api_code: str, param_desc: str):
    """Take a stub function and make it into a subcommand
    that returns the corresponding API data.
    """
    def decorator(func: Callable):
        assert func.__doc__ is not None
        param_name = [key for key, value in func.__annotations__.items()
                      if value is str or value == 'str'][0]
        @group.command(name=func.__name__, description=func.__doc__)
        @app_commands.describe(**{param_name: param_desc})
        @wraps(func)
        async def subcommand(ctx: discord.Interaction, **kwargs):
            word = kwargs[param_name]
            await ctx.response.defer()
            resp = await fetch_words(**{api_code: word})
            await ctx.edit_original_response(
                embed=format_words(ctx, api_code, word, resp))
        return subcommand
    return decorator

### /words <command> <arg>:<thing>

words = app_commands.Group(
    name='words', description="""Lexical data related to words!""")

### rhyming is a special case

@words.command()
@app_commands.rename(word='with')
@app_commands.describe(word='The word that other words rhyme with.')
async def rhyming(ctx: discord.Interaction, word: str):
    """Words that rhyme with a word."""
    await ctx.response.defer()
    perf: list[WordResp] = await fetch_words(rel_rhy=word, md='s')
    near: list[WordResp] = await fetch_words(rel_nry=word, md='s')
    key = itemgetter('numSyllables')
    perf.sort(key=key)
    near.sort(key=key)
    comma = mkmsg(ctx, ',')
    fields = []
    for count, results in groupby(perf, key):
        fields.append((
            Msg('words/syllable-count', count),
            comma.join(result['word'] for result in results),
            False
        ))
    perf_embed = mkembed(ctx,
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
    near_embed = mkembed(ctx,
        Msg('words/near-rhymes'),
        # no description if any rhymes were found
        description=None if fields else Msg('none-paren'),
        fields=fields,
        color=0xe67e22
    )
    await ctx.edit_original_response(embeds=[perf_embed, near_embed])

@endpoint(words, 'ml', 'A phrase.')
async def meaning(ctx: discord.Interaction, phrase: str):
    """Words that mean something."""

@endpoint(words, 'sl', 'The sound.')
async def sounding(ctx: discord.Interaction, like: str):
    """Words that sound like something."""

@endpoint(
    words, 'sp',
    'The spelling. Wildcards allowed - use `re*ing` to get words starting '
    'with re- and ending with -ing')
async def spelled(ctx: discord.Interaction, like: str):
    """Words that are spelled like something."""

@endpoint(words, 'rel_jja', 'An adjective.')
async def modified(ctx: discord.Interaction, by: str):
    """Popular nouns modified by the given adjective, \
per Google Books Ngrams."""

@endpoint(words, 'rel_jjb', 'A noun.')
async def modifying(ctx: discord.Interaction, word: str):
    """Popular adjectives used to modify the given noun, \
per Google Books Ngrams."""

@endpoint(words, 'rel_trg', 'A word.')
async def associated(ctx: discord.Interaction, word: str):
    """Words that are statistically associated with the query word \
in the same piece of text."""

@endpoint(words, 'rel_bga', 'A word.')
async def after(ctx: discord.Interaction, word: str):
    """Frequent predecessors of the given word (per Google Books Ngrams)."""

@endpoint(words, 'rel_bgb', 'A word.')
async def before(ctx: discord.Interaction, word: str):
    """Words that frequently follow the given word \
(per Google Books Ngrams)."""

### /lex <command> <arg>:<word>

lex = app_commands.Group(
    name='lex', description="""Lexical data related to words!""")

@endpoint(lex, 'rel_syn', 'A word.')
async def synonyms(ctx: discord.Interaction, word: str):
    """Synonyms of the given word (per WordNet)."""

@endpoint(lex, 'rel_ant', 'A word.')
async def antonyms(ctx: discord.Interaction, word: str):
    """Antonyms of the given word (per WordNet)."""

@endpoint(lex, 'rel_spc', 'A word.')
async def hypernyms(ctx: discord.Interaction, word: str):
    """Hypernyms (words that are more general than the word, per WordNet)."""

@endpoint(lex, 'rel_gen', 'A word.')
async def hyponyms(ctx: discord.Interaction, word: str):
    """Hyponyms (words that are more specific than the word, per WordNet)."""

@endpoint(lex, 'rel_com', 'A word.')
async def holonyms(ctx: discord.Interaction, word: str):
    """Holonyms (words that are a part of the word, per WordNet)."""

@endpoint(lex, 'rel_par', 'A word.')
async def meronyms(ctx: discord.Interaction, word: str):
    """Meronyms (words that the word is part of, per WordNet)."""

@endpoint(lex, 'rel_hom', 'A word.')
async def homophones(ctx: discord.Interaction, word: str):
    """Homophones (words that sound alike)."""

@endpoint(lex, 'rel_cns', 'A word.')
async def homoconsonants(ctx: discord.Interaction, word: str):
    """Words that match consonants."""

def setup(bot: commands.Bot):
    global session
    session = aiohttp.ClientSession()
    for cmd in {words, lex}:
        bot.tree.add_command(cmd)
