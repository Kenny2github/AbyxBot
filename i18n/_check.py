import os
import sys
import json
import argparse
from AbyxBot.lib.utils import recurse_mtimes
from AbyxBot.i18n.load_i18n import load_i18n_strings, SUPPORTED_LANGS, ROOT

parser = argparse.ArgumentParser(
    description='Run i18n auditing or view/modify strings.')
subparsers = parser.add_subparsers(
    dest='cmd', required=True, title='Subcommands?')

audit_parser = subparsers.add_parser(
    'audit', description='Run i18n auditing.')
audit_parser.add_argument('-a', action='store_true', default=False,
                          help='Show all i18n calls.')

view_parser = subparsers.add_parser(
    'view', description='View i18n string(s).')
view_parser.add_argument('--lang', choices=SUPPORTED_LANGS,
                         default='en', help='The language of i18n to view.')
view_parser.add_argument('keys', nargs='+', help='The i18n key(s) to view.')

change_parser = subparsers.add_parser(
    'change', description='Change an i18n string.')
change_parser.add_argument('--lang', choices=SUPPORTED_LANGS,
                           default='en', help='The language of i18n to change.')
change_parser.add_argument('key', help='The i18n key to modify.')

stub_parser = subparsers.add_parser(
    'stub', description='Generate i18n stubs for non-English languages.')
stub_parser.add_argument('--dir', default=None,
                         help='The i18n directory.')
stub_parser.add_argument('--lang', default='qqq',
                         help='The language to generate stubs for.')

def audit(cmdargs: argparse.Namespace):
    """Conduct an audit of i18n string use and presence."""
    mtimes = recurse_mtimes('AbyxBot')
    pyfiles = {key for key in mtimes.keys() if key.endswith('.py')}
    contents: dict[str, str] = {}
    for fname in pyfiles:
        with open(fname) as f:
            contents[fname] = f.read()
    all_contents = ''.join(contents.values())

    strings = load_i18n_strings()

    if cmdargs.a:
        for fn, content in contents.items():
            print(fn + ':')
            lines = content.splitlines()
            for lineno, line in enumerate(lines, start=1):
                for check in 'mkmsg(', 'Msg(', '_(', 'maker(':
                    if check in line:
                        break
                else:
                    continue
                if lineno > 1:
                    print(lineno-1, lines[lineno-2])
                print(lineno, line)
                if lineno < len(lines):
                    print(lineno+1, lines[lineno])
                print()
            print()

    print('----------------------')
    status = 0
    for key in strings['en']:
        for lang, lang_strings in strings.items():
            if lang_strings.get(key, '__MISSING__') == '__MISSING__' \
                    and lang != 'qqx':
                print('lang', lang, 'missing', key)
                status = 1
        if key not in all_contents:
            print('unused key:', key)
            status = 1
    for lang, lang_strings in strings.items():
        for key in lang_strings:
            if key not in strings['en']:
                print('extra key', key, 'in lang', lang)
    sys.exit(status)

def view(cmdargs: argparse.Namespace):
    """View i18n string(s)."""
    strings = load_i18n_strings()
    default = '--(No i18n set for this key in this language)--'
    if len(cmdargs.keys) == 1:
        print(strings[cmdargs.lang].get(cmdargs.keys[0], default))
    else:
        for key in cmdargs.keys:
            print(key + ':')
            print(strings[cmdargs.lang].get(key, default))

def change(cmdargs: argparse.Namespace):
    lang = cmdargs.lang
    try:
        dirname, key = cmdargs.key.rsplit('/', 1)
    except TypeError:
        key = cmdargs.key
        fname = os.path.join(ROOT, f'{lang}.json')
    else:
        dirname = dirname.replace('/', os.pathsep)
        os.makedirs(os.path.join(ROOT, dirname), exist_ok=True)
        fname = os.path.join(ROOT, dirname, f'{lang}.json')
    try:
        with open(fname) as f:
            strings = json.load(f)
    except FileNotFoundError:
        strings = {}
    strings[key] = sys.stdin.read().strip()
    with open(fname, 'w') as f:
        json.dump(strings, f, indent='\t')

def stub(cmdargs: argparse.Namespace):
    lang = cmdargs.lang
    if cmdargs.dir is None:
        langname = os.path.join(ROOT, f'{lang}.json')
        enname = os.path.join(ROOT, 'en.json')
    else:
        langname = os.path.join(ROOT, cmdargs.dir, f'{lang}.json')
        enname = os.path.join(ROOT, cmdargs.dir, 'en.json')
    try:
        with open(enname) as f:
            enstrings: dict[str, str] = json.load(f)
    except FileNotFoundError:
        stub_parser.error(f'Missing en.json for {cmdargs.dir}')
    try:
        with open(langname) as f:
            langstrings: dict[str, str] = json.load(f)
    except FileNotFoundError:
        langstrings = {}
    missing = set(enstrings.keys()) - set(langstrings.keys())
    if missing:
        print('Generating', lang, 'stubs for', end=' ')
        for key in enstrings.keys():
            if key not in langstrings:
                print(key, end=' ')
                langstrings[key] = '__MISSING__'
        with open(langname, 'w') as f:
            json.dump(langstrings, f, indent='\t')

def main(args: list[str]):
    cmdargs = parser.parse_args(args[1:])
    globals()[cmdargs.cmd](cmdargs)

if __name__ == '__main__':
    main(sys.argv)
