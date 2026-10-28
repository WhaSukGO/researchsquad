"""A deliberately narrow beat-alignment check for one rhythmic **kern spine.

Null melody rows with a chord carry no explicit time: refuse to guess. This is
an extra diagnostic, not a general Humdrum rhythm interpreter or gold audit.
"""
from fractions import Fraction
import re
from scorebench.metrics import chord_from_label

VERSION = 'single-spine-explicit-onsets-v1'


def timed_chords(text):
    headers = next(line.split('\t') for line in text.splitlines() if line.startswith('**'))
    if headers.count('**kern') != 1 or headers.count('**mxhm') != 1 or len(headers) != 2:
        raise ValueError('Timing diagnostic requires exactly **kern and **mxhm')
    ki, ci = headers.index('**kern'), headers.index('**mxhm')
    cursor = Fraction(0); result = []
    for line in text.splitlines():
        if not line or line.startswith(('!', '*', '=')):
            if line.startswith('*') and any(x in {'*^','*v','*x','*+'} for x in line.split('\t')):
                raise ValueError('Unsupported spine transition')
            continue
        cells = line.split('\t')
        if len(cells) != 2:raise ValueError('Inconsistent spine width')
        note, chord = cells[ki], cells[ci]
        if note == '.':
            if chord != '.':raise ValueError('Chord on a null melody row: onset is not explicitly encoded')
            continue
        if ' ' in note:raise ValueError('Polyphonic/chord token unsupported')
        match = re.search(r'(0+|[1-9][0-9]*)(%[0-9]+)?(\.*)', note)
        if not match:raise ValueError('Explicit duration required')
        if chord != '.':result.append((str(cursor), chord_from_label(chord)))
        number, ratio, dots = match.groups()
        duration = Fraction(4, int(number)) if int(number) else Fraction(4 * 2 ** len(number))
        if ratio:duration *= int(ratio[1:])
        duration *= sum(Fraction(1, 2**i) for i in range(len(dots)+1))
        if 'q' not in note:cursor += duration
    return result
