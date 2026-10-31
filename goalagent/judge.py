"""Deterministic judge rules for 1988-era discourse. No model involved.

A message passes when it uses no post-1988 vocabulary, cites only IDs in the speaker's
view (or [conj:...] tags), attaches an ID to every sentence that states a number, and
calls something verified only when a supported claim ID backs the sentence.
"""
import re

BLACKLIST=['convolutional network','convolutional net','convnet','cnn','max pool','max-pool','pooling layer','lenet','relu','dropout',
           'batch norm','gpu','imagenet','mnist','deep learning','pytorch','tensorflow','transformer','backprop through time','adam optimizer']
CITE=re.compile(r'\[([A-Za-z0-9_#:.-]+)\]')
NUMBER=re.compile(r'(\d+(?:\.\d+)?\s*%|\b0\.\d+\b|\b\d{1,3}(?:,\d{3})+\b|\b\d{4,}\b)')
VERIFIED=re.compile(r'\b(verified|proven|confirmed|established|supported|demonstrated)\b',re.I)


def sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+',text) if s.strip()]


def check_text(text,view_ids,supported_ids=()):
    """Return a list of (rule, detail) violations; empty means pass."""
    violations=[];low=text.lower()
    for phrase in BLACKLIST:
        if re.search(r'(?<![a-z])'+re.escape(phrase)+r'(?![a-z])',low):violations.append(('vocabulary',phrase))
    view=set(view_ids);supported=set(supported_ids)
    for cite in CITE.findall(text):
        if cite.startswith('conj:'):continue
        if cite not in view:violations.append(('unknown_citation',cite))
    for s in sentences(text):
        cites=CITE.findall(s)
        if NUMBER.search(re.sub(r'\[[^\]]*\]','',s)) and not cites:violations.append(('uncited_number',s[:100]))
        if VERIFIED.search(s) and not any(c in supported for c in cites) and not any(c.startswith('conj:') for c in cites):
            violations.append(('unsupported_verification',s[:100]))
    return violations


def describe(violations):
    names={'vocabulary':'post-1988 vocabulary','unknown_citation':'citation outside your ledger view','uncited_number':'a number without a ledger ID','unsupported_verification':'calls something verified without a supported claim ID'}
    return '; '.join(f'{names[r]}: {d}' for r,d in violations)
