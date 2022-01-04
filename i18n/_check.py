import sys
import json
import argparse
from AbyxBot.utils import recurse_mtimes
from AbyxBot.load_i18n import load_i18n_strings, SUPPORTED_LANGS, ROOT

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
                for check in '.msg(', 'Msg(':
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
        for lang in strings.keys():
            if strings[lang].get(key) is None and lang != 'qqx':
                print(lang, 'missing', key)
                status = 1
        if key not in all_contents:
            print(key, 'unused')
            status = 1
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
    try:
        dirname, key = cmdargs.key.rsplit('/', 1)
    except TypeError:
        dirname, key = None, cmdargs.key
    lang = cmdargs.lang
    if dirname:
        fname = f'{ROOT}/{dirname}/{lang}.json'
    else:
        fname = f'{ROOT}/{lang}.json'
    with open(fname) as f:
        strings = json.load(f)
    strings[key] = sys.stdin.read().strip()
    with open(fname, 'w') as f:
        json.dump(strings, f, indent=2)

def main(args: list[str]):
    cmdargs = parser.parse_args(args[1:])
    globals()[cmdargs.cmd](cmdargs)

if __name__ == '__main__':
    main(sys.argv)
