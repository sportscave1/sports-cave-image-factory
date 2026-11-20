"""Lossless category editing with immutable section boundaries."""
from prompt_library import Prompt, digest, validate_text


def is_bundle(prompt):
    return prompt.path.startswith('@category/')


def opening(prompt):
    return f'<<<SECTION {prompt.key}: {prompt.title}>>>\n'


def closing(prompt):
    return f'\n<<<END {prompt.key}>>>'


def combine(prompts, texts=None):
    texts = texts or {}
    return '\n\n'.join(opening(p) + texts.get(p.key, p.text) + closing(p) for p in prompts)


def bundle_prompt(prompts, category):
    return Prompt('@category/' + category, '', category, combine(prompts))


def split(prompts, text):
    result = {}
    remaining = text
    for index, prompt in enumerate(prompts):
        prefix = ('\n\n' if index else '') + opening(prompt)
        if not remaining.startswith(prefix):
            raise ValueError('Keep every SECTION and END heading unchanged and in the same order.')
        remaining = remaining[len(prefix):]
        end = closing(prompt)
        if remaining.count(end) != 1:
            raise ValueError('Keep every SECTION and END heading unchanged and in the same order.')
        value, remaining = remaining.split(end, 1)
        validate_text(prompt.text, value)
        result[prompt.key] = value
    if remaining:
        raise ValueError('Place changes inside a section, before its END heading.')
    return result


def changes(prompt, text, prompts):
    rows = [p for p in prompts if p.category == prompt.category]
    before = split(rows, prompt.text)
    after = split(rows, text)
    return [{'path': p.path, 'symbol': p.symbol, 'key': p.key,
             'base_hash': digest(before[p.key]), 'text': after[p.key]}
            for p in rows if before[p.key] != after[p.key]]
