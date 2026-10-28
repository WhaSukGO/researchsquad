from pathlib import Path
import hashlib, json, re, sys, tempfile, xml.etree.ElementTree as ET
import music21 as m21
import converter21
converter21.register()
ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / 'candidate-config.json').read_text())
INPUT = ROOT / CONFIG['input_directory']
BASE = INPUT / 'baselines' / 'audiveris-enlarged'
HARTE = {'C:maj':'C major','C:maj/3':'C major/E','G:maj/3':'G major/B','A:min7':'A minor-seventh','F:maj7':'F major-seventh','C:maj/5':'C major/G','D:min/b7':'D minor/C','A:min':'A minor'}
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def parse(path):
    return m21.converter.parse(str(path), format='humdrum', forceSource=True)
def events(score):
    return [(float(n.getOffsetInHierarchy(score)), float(n.duration.quarterLength), tuple(p.nameWithOctave for p in n.pitches)) for n in score.recurse().notes if not isinstance(n, m21.harmony.ChordSymbol)]
def harmonies(score):
    return [(float(h.getOffsetInHierarchy(score)), h.root().name, h.chordKind, h.bass().name) for h in score.recurse().getElementsByClass(m21.harmony.ChordSymbol)]
def canonical(score, dest):
    score.write('humdrum', fp=str(dest))
    lines = dest.read_text().splitlines()
    # Converter21 exports harmony as Harte; translate only the observed source vocabulary.
    out=[]
    for line in lines:
        fields=line.split('\t')
        if '**harte' in fields:
            fields=['**mxhm' if f=='**harte' else f for f in fields]
        elif not line.startswith(('!', '*', '=')):
            fields=[HARTE.get(f,f) for f in fields]
            for f in fields:
                if re.match(r'^[A-G][b#]?:',f):
                    raise ValueError('Unmapped exported harmony: '+f)
        out.append('\t'.join(fields))
    dest.write_text('\n'.join(out)+'\n')
def add_empty_harmony(text):
    if '**mxhm' in text:
        return text
    out=[]
    for line in text.splitlines():
        if not line or line.startswith('!!'):
            out.append(line); continue
        f=line.split('\t')
        if '**kern' in f: extra='**mxhm'
        elif all(x=='*-' for x in f): extra='*-'
        elif line.startswith('*'): extra='*'
        elif line.startswith('='): extra=f[0]
        elif line.startswith('!'): extra='!'
        else: extra='.'
        out.append(line+'\t'+extra)
    return '\n'.join(out)+'\n'
def build():
    records=[]
    for sample in CONFIG['samples']:
        dest=ROOT/(sample+'.krn')
        repairs=[]
        if sample != 'sample-029':
            source=BASE/(sample+'.krn')
            before=parse(source)
            if sample in CONFIG['preserve_verbatim']:
                dest.write_text(add_empty_harmony(source.read_text()))
                method='Supplied kern preserved; empty harmony spine appended only when absent.'
            else:
                canonical(before,dest)
                dest.write_text(add_empty_harmony(dest.read_text()))
                method='Supplied kern parsed with converter21 and canonically re-exported; source harmonies retained through explicit Harte-to-mxhm mapping.'
                repairs.append('Canonical serialization normalizes malformed tokens, ties and spine structure; this is not a manual melody correction.')
        else:
            source=BASE/(sample+'.musicxml')
            tree=ET.parse(source)
            for div in tree.findall('.//divisions'):
                if div.text=='0':
                    div.text='1'
                    repairs.append('Invalid divisions=0 replaced with 1. Note durations are reconstructed from explicit type/dot, not original duration=1.')
            durations={'whole':4,'half':2,'quarter':1,'eighth':0.5,'16th':0.25,'32nd':0.125}
            for note in tree.findall('.//note'):
                typ=note.findtext('type')
                if typ not in durations: raise ValueError('Unknown note type '+str(typ))
                q=durations[typ]*sum(0.5**i for i in range(len(note.findall('dot'))+1))
                if q != int(q): raise ValueError('This repair requires integer duration with divisions=1')
                duration=note.find('duration')
                if duration is not None: duration.text=str(int(q))
            repaired=ROOT/'sample-029-repaired.musicxml'
            tree.write(repaired,encoding='utf-8',xml_declaration=True)
            before=m21.converter.parse(str(repaired),format='musicxml',forceSource=True)
            canonical(before,dest)
            dest.write_text(add_empty_harmony(dest.read_text()))
            method='Supplied MusicXML repaired using explicit half-note types, then converted with converter21 registered.'
            repairs.append('Only supplied D4 and B3 pitches retained. Empty measures and omitted material remain unresolved; no image melody reconstruction attempted.')
        after=parse(dest)
        chords_before=harmonies(before); chords_after=harmonies(after)
        if [(x[1:]) for x in chords_before] != [(x[1:]) for x in chords_after]:
            raise AssertionError((sample,'source harmony sequence changed',chords_before,chords_after))
        records.append({'sample':sample,'source':str(source.relative_to(ROOT)),'source_sha256':digest(source),'image':str((INPUT/'images'/(sample+'.png')).relative_to(ROOT)),'artifact':dest.name,'artifact_sha256':digest(dest),'method':method,'repairs':repairs,'source_note_events':len(events(before)),'output_note_events':len(events(after)),'source_duration':float(before.duration.quarterLength),'output_duration':float(after.duration.quarterLength),'source_harmonies':chords_before,'output_harmonies':chords_after,'exact_event_preservation':events(before)==events(after),'parse_ok':True})
    (ROOT/'provenance.json').write_text(json.dumps(records,indent=2)+'\n')
    return records
if __name__=='__main__':
    print(json.dumps(build(),indent=2))
