import re
from typing import Generator

TOKENS: dict[str, tuple[bool, str]] = {
    '': (False, 'p'),
    '```': (True, 'pre'),
    '`': (True, 'code'),
    '||': (True, 'abbr'),
    '**': (True, 'b'),
    '*': (True, 'i'),
    '__': (True, 'u'),
    '_': (True, 'i'),
    '~~': (True, 's'),
    '> ': (False, 'quote'),
}
TAGS = {tag: (closed, token) for token, (closed, tag) in TOKENS.items()}

SPECIAL = re.compile(r'<[:@#][^>]+>|:[^:]+:')

class RetSaveGen:
    """Generator wrapper that saves the return value of the generator.
    Adapted from https://stackoverflow.com/a/34073559/6605349
    """
    def __init__(self, gen: Generator):
        self.gen = gen
        self.value = None

    def __iter__(self):
        self.value = yield from self.gen

def test_tokens(text: str, start: int, allow_p: bool = True) -> Generator[str, None, int]:
    """Try a position to see if a token can be opened here."""
    pointer = start
    for tkn, (closed, tag) in TOKENS.items():
        if closed and text.startswith(tkn, pointer):
            pointer = yield from close_token(text, tkn, tag, pointer + len(tkn))
            break
        if not closed and (pointer == 0 or text[pointer-1] == '\n') \
                and (tkn or allow_p) and text.startswith(tkn, pointer):
            pointer = yield from end_token(text, tkn, tag, pointer + len(tkn))
            break
    else:
        yield text[pointer]
        pointer += 1
    return pointer

def close_token(text: str, token: str, tag: str, start: int) -> Generator[str, None, int]:
    """Return upon finding the closing side of a Markdown token."""
    tokens: list[str] = [f'<{tag}>']
    pointer = start
    while pointer < len(text):
        if text.startswith(token, pointer):
            tokens.append(f'</{tag}>')
            pointer += len(token)
            break
        gen = RetSaveGen(test_tokens(text, pointer))
        tokens.extend(gen)
        pointer = gen.value
    else:
        tokens[0] = token # never closed, replace opening with original token
    yield from tokens
    return pointer

def end_token(text: str, token: str, tag: str, start: int) -> Generator[str, None, int]:
    """Return finding the end of a line-closed token."""
    yield f'<{tag}>'
    pointer = start
    while pointer < len(text):
        if text[pointer] == '\n':
            yield f'</{tag}>'
            pointer += 1
            break
        pointer = yield from test_tokens(text, pointer, bool(token))
    else:
        yield f'</{tag}>' # end of string
    return pointer

def html_tokenize(text: str) -> Generator[str, None, int]:
    """Tokenize the Markdown and convert the tokens to HTML tags."""
    pointer = 0
    while pointer < len(text):
        pointer = yield from test_tokens(text, pointer)
    return pointer

def md_to_html(text: str) -> str:
    """Parse Markdown into HTML."""
    if text.startswith('>>> '):
        return '<blockquote>' + md_to_html(text[4:]) + '</blockquote>'
    return ''.join(html_tokenize(text))

def html_to_md(text: str) -> str:
    """Unparse Markdown from HTML."""
    for tag, (closed, token) in TAGS.items():
        text = text.replace(f'<{tag}>', token)
        text = text.replace(f'</{tag}>', token if closed else '\n')
    return text