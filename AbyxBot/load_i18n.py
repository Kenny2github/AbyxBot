import os
import json
from warnings import warn

ROOT = 'i18n'
SUPPORTED_LANGS = set(
    fn[:-5] for fn in os.listdir(ROOT) if fn.endswith('.json'))

def load_strings() -> None:
    """Load translation strings synchronously."""
    unformatted: dict[str, dict[str, str]] = {}
    for lang in SUPPORTED_LANGS:
        with open(os.path.join(ROOT, f'{lang}.json')) as f:
            data: dict = json.load(f)
        unformatted.setdefault(lang, {}).update(data)
    for dirname in os.listdir(ROOT):
        if not os.path.isdir(os.path.join(ROOT, dirname)):
            continue # now dirname is an actual dir name
        for lang in SUPPORTED_LANGS:
            path = os.path.join(ROOT, dirname, f'{lang}.json')
            try:
                with open(path) as f:
                    data: dict = json.load(f)
            except FileNotFoundError:
                if lang != 'qqx': # qqx only needs one file
                    warn(f'No {lang} i18n for {dirname}/', UserWarning)
                continue
            for key, string in data.items():
                unformatted[lang][f'{dirname}/{key}'] = string
    return unformatted