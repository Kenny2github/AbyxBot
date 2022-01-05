ZWNJ = '\N{ZERO WIDTH NON-JOINER}'
LABR = '\N{MATHEMATICAL LEFT ANGLE BRACKET}'
RABR = '\N{MATHEMATICAL RIGHT ANGLE BRACKET}'
DONE = '\N{WHITE HEAVY CHECK MARK}'

# regional indicators, for use in flags
REGI = tuple(chr(0x1f1e6 + i) for i in range(26)) # indexes
REGU = {chr(0x41 + i): reg for i, reg in enumerate(REGI)} # uppercase letters
REGL = {letter.lower(): reg for letter, reg in REGU.items()} # lowercase ''