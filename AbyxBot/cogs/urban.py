# stdlib
import re
from datetime import datetime
from urllib.parse import urlencode
from typing import TypedDict, Match

# 3rd-party
import discord
from discord import app_commands
from discord.ext import commands

# 1st-party
from ..i18n import error_embed, Msg, mkembed
from .words import session

# NOTE: These TypedDicts only include fields we use

class UrbanDefinition(TypedDict):
    definition: str
    permalink: str
    thumbs_up: int
    author: str
    word: str
    written_on: str
    example: str
    thumbs_down: int

class UrbanResp(TypedDict):
    list: list[UrbanDefinition]

def make_word_link(match: Match[str]) -> str:
    word = match.group(1)
    url = 'https://www.urbandictionary.com/define.php?' \
        + urlencode({'term': word})
    return f'[{word}]({url})'

def linkify(defn: str) -> str:
    return re.sub(r'\[([^\]]+)\]', make_word_link, defn)

@app_commands.command()
@app_commands.describe(
    word='A word (or sometimes phrase).',
    top_n='Only return the top N definitions',
    min_score='Only return definitions with at least this net score.',
)
async def urban(
    ctx: discord.Interaction, word: str,
    top_n: app_commands.Range[int, 1, 10] = 3,
    min_score: int = 0,
):
    """Urban Dictionary definition of a word/phrase."""
    await ctx.response.defer()
    URBAN_URL = 'https://api.urbandictionary.com/v0/define'
    defns: list[UrbanDefinition] = []
    async with session.get(URBAN_URL, params={'term': word}) as resp:
        if resp.ok:
            data: UrbanResp = await resp.json()
            defns.extend(data['list'])
    if not defns:
        await ctx.edit_original_response(
            embed=error_embed(ctx, Msg('words/no-def', word)))
        return
    # filter out definitions under minimum score
    defns = [defn for defn in defns
             if defn['thumbs_up'] - defn['thumbs_down'] >= min_score]
    # reduce to top N definitions
    defns.sort(key=lambda defn: defn['thumbs_up'] - defn['thumbs_down'],
               reverse=True)
    defns = defns[:top_n]
    # construct definition embeds
    embeds: list[discord.Embed] = []
    for i, defn in enumerate(defns, start=1):
        embed = mkembed(
            ctx, title=Msg('urban/defn-title', i, defn['word']),
            description=linkify(defn['definition']),
            fields=(
                (Msg('urban/votes-title'), Msg(
                    'urban/votes', defn['thumbs_up'] - defn['thumbs_down'],
                    defn['thumbs_up'], defn['thumbs_down'],
                ), True),
                (Msg('urban/example'), linkify(defn['example']), False),
            ),
            timestamp=datetime.strptime(defn['written_on'],
                                        '%Y-%m-%dT%H:%M:%S.%f%z'),
            url=defn['permalink'],
            color=0xfffffe,
            footer=Msg('urban/src-urban'),
        )
        embed.set_author(name=defn['author'])
        embeds.append(embed)
    await ctx.edit_original_response(embeds=embeds)

def setup(bot: commands.Bot):
    bot.tree.add_command(urban)
