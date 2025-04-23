from __future__ import annotations
# stdlib
import re
from typing import TYPE_CHECKING, TypedDict, Optional
from operator import itemgetter
from itertools import groupby

# 3rd-party
import discord
from discord import app_commands

# 1st-party
from ..lib.database import db
from ..i18n import Msg, mkembed, mkmsg, error_embed
if TYPE_CHECKING:
    from ..lib.client import AbyxBot

API_URL = 'https://api.datamuse.com/words'

class WordResp(TypedDict):
    score: int
    word: str
    tags: list[str]
    numSyllables: int
    defs: list[str]
    defHeadword: str

async def fetch_words(ctx: discord.Interaction[AbyxBot], /, **kwargs) -> list[WordResp]:
    """Get API data, passing kwargs."""
    async with ctx.client.session.get(API_URL, params=kwargs) as resp:
        data: list[WordResp] = await resp.json()
    if ctx.guild_id:
        censor = await db.guild_words_censor(ctx.guild_id)
        if censor:
            data = [d for d in data if not re.search(censor, d['word'])]
    return data

@app_commands.command()
@app_commands.describe(
    meaning='[ml] Words that mean this.',
    sounding_like='[sl] Words that sound like this.',
    spelled_like='[sp] Words that are spelled like this - wildcards allowed: '
    'https://onelook.com/thesaurus/#patterns',
    modified_by='[rel_jja] Popular nouns modified by this adjective, per '
    'Google Books Ngrams.',
    modifying='[rel_jjb] Popular adjectives used to modify this noun, per '
    'Google Books Ngrams.',
    associated_with='[rel_trg] Words that are statistically associated with '
    'this word in the same piece of text.',
    after='[rel_bga] Frequent predecessors of this word (per Google Books '
    'Ngrams).',
    before='[rel_bgb] Words that frequently follow this word (per Google '
    'Books Ngrams).',
    synonymizing='[rel_syn] Synonyms of this word (per WordNet).',
    antonymizing='[rel_ant] Antonyms of this word (per WordNet).',
    hypernymizing='[rel_spc] Hypernyms (words that are more general than this '
    'word, per WordNet).',
    hyponymizing='[rel_gen] Hyponyms (words that are more specific than this '
    'word, per WordNet).',
    holonymizing='[rel_com] Holonyms (words that are a part of this word, per '
    'WordNet).',
    meronymizing='[rel_par] Meronyms (words that this word is part of, per '
    'WordNet).',
    homophonizing='[rel_hom] Homophones (words that sound alike).',
    consonantizing='[rel_cns] Words that match consonants.',
    topics='Bias words related to these words to appear first.'
)
async def words(
    ctx: discord.Interaction[AbyxBot],
    meaning: Optional[str] = None,
    sounding_like: Optional[str] = None,
    spelled_like: Optional[str] = None,
    modified_by: Optional[str] = None,
    modifying: Optional[str] = None,
    associated_with: Optional[str] = None,
    after: Optional[str] = None,
    before: Optional[str] = None,
    synonymizing: Optional[str] = None,
    antonymizing: Optional[str] = None,
    hypernymizing: Optional[str] = None,
    hyponymizing: Optional[str] = None,
    holonymizing: Optional[str] = None,
    meronymizing: Optional[str] = None,
    homophonizing: Optional[str] = None,
    consonantizing: Optional[str] = None,
    topics: Optional[str] = None,
):
    """Lexical data related to words! Parameters can be combined."""
    kwargs = {
        'ml': meaning,
        'sl': sounding_like,
        'sp': spelled_like,
        'rel_jja': modified_by,
        'rel_jjb': modifying,
        'rel_trg': associated_with,
        'rel_bga': after,
        'rel_bgb': before,
        'rel_syn': synonymizing,
        'rel_ant': antonymizing,
        'rel_spc': hypernymizing,
        'rel_gen': hyponymizing,
        'rel_com': holonymizing,
        'rel_par': meronymizing,
        'rel_hom': homophonizing,
        'rel_cns': consonantizing,
        'topics': topics,
    }
    kwargs = {key: value for key, value in kwargs.items() if value is not None}
    if not kwargs:
        await ctx.response.send_message(embed=error_embed(ctx, 'words/no-request'))
        return
    await ctx.response.defer()
    data: list[WordResp] = await fetch_words(ctx, **kwargs)
    await ctx.edit_original_response(embed=mkembed(ctx,
        title=Msg('words/title'),
        description=mkmsg(ctx, ',').join(
            '{score}: {word}'.format(**i)
            for i in data
        ) or Msg('none-paren'),
        color=discord.Color.blue()
    ))

### rhyming is a special case

@app_commands.command()
@app_commands.rename(word='with')
@app_commands.describe(word='The word that other words rhyme with.')
async def rhymes(ctx: discord.Interaction[AbyxBot], word: str):
    """Words that rhyme with a word."""
    await ctx.response.defer()
    perf: list[WordResp] = await fetch_words(ctx, rel_rhy=word, md='s')
    near: list[WordResp] = await fetch_words(ctx, rel_nry=word, md='s')
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

def setup(bot: AbyxBot):
    bot.tree.add_command(words)
    bot.tree.add_command(rhymes)
