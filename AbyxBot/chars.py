ZWSP = '\N{ZERO WIDTH SPACE}'
ZWNJ = '\N{ZERO WIDTH NON-JOINER}'
LABR = '\N{MATHEMATICAL LEFT ANGLE BRACKET}'
RABR = '\N{MATHEMATICAL RIGHT ANGLE BRACKET}'
DONE = '\N{WHITE HEAVY CHECK MARK}'

# regional indicators, for use in flags
REGI = tuple(chr(0x1f1e6 + i) for i in range(26)) # indexes
REGU = {chr(0x41 + i): reg for i, reg in enumerate(REGI)} # uppercase letters
REGL = {letter.lower(): reg for letter, reg in REGU.items()} # lowercase ''
NUMS = tuple(
    '%s\N{VARIATION SELECTOR-16}\N{COMBINING ENCLOSING KEYCAP}' % i
    for i in range(10)
) + ('\N{KEYCAP TEN}',)

UP = '<:up:932162569731473438>'
DOWN = '<:down:932162569790193695>'
LEFT = '<:left:932162569530126388>'
RIGHT = '<:right:932162569362358293>'

BLACK_SQUARE = '\N{BLACK LARGE SQUARE}'
WHITE_SQUARE = '\N{WHITE LARGE SQUARE}'

BLUE_CIRCLE = '\N{LARGE BLUE CIRCLE}'
RED_CIRCLE = '\N{LARGE RED CIRCLE}'
