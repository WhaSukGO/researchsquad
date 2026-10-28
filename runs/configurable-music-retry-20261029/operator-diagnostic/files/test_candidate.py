from pathlib import Path
import json, unittest
import build_candidate as b
class CandidateTests(unittest.TestCase):
    def test_structure_and_parse(self):
        for sample in b.CONFIG['samples']:
            with self.subTest(sample=sample):
                path=b.ROOT/(sample+'.krn'); text=path.read_text()
                self.assertIn('**kern',text); self.assertIn('**mxhm',text)
                width=None; terminated=False
                for line in text.splitlines():
                    if not line or line.startswith('!!'): continue
                    cells=line.split('\t')
                    if width is None:
                        self.assertTrue(all(c.startswith('**') for c in cells)); width=len(cells)
                    self.assertEqual(len(cells),width, line)
                    if '*^' in cells: width+=cells.count('*^')
                    if '*v' in cells:
                        groups=0; in_group=False
                        for c in cells:
                            if c=='*v' and not in_group: groups+=1
                            in_group=c=='*v'
                        width-=cells.count('*v')-groups
                    if all(c=='*-' for c in cells): terminated=True; width=0
                self.assertTrue(terminated)
                score=b.parse(path)
                self.assertGreater(len(b.events(score)),0)
                self.assertNotIn('**harte',text)
    def test_transposition(self):
        results=[]
        for sample in b.CONFIG['samples']:
            with self.subTest(sample=sample):
                score=b.parse(b.ROOT/(sample+'.krn'))
                shifted=score.transpose('M2')
                back=shifted.transpose('-M2')
                notes=[n for n in score.recurse().notes if not isinstance(n,b.m21.harmony.ChordSymbol)]
                moved=[n for n in shifted.recurse().notes if not isinstance(n,b.m21.harmony.ChordSymbol)]
                self.assertEqual(len(notes),len(moved))
                for a,c in zip(notes,moved):
                    self.assertEqual(float(a.duration.quarterLength),float(c.duration.quarterLength))
                    self.assertEqual([float(p.ps)+2 for p in a.pitches],[float(p.ps) for p in c.pitches])
                chords=list(score.recurse().getElementsByClass(b.m21.harmony.ChordSymbol))
                changed=list(shifted.recurse().getElementsByClass(b.m21.harmony.ChordSymbol))
                self.assertEqual(len(chords),len(changed))
                for a,c in zip(chords,changed):
                    self.assertEqual((a.root().pitchClass+2)%12,c.root().pitchClass)
                    self.assertEqual((a.bass().pitchClass+2)%12,c.bass().pitchClass)
                    self.assertEqual(a.chordKind,c.chordKind)
                    self.assertEqual(a.getOffsetInHierarchy(score),c.getOffsetInHierarchy(shifted))
                self.assertEqual(b.events(score),b.events(back))
                self.assertEqual(b.harmonies(score),b.harmonies(back))
                results.append({'sample':sample,'note_events':len(notes),'chords':len(chords),'up_M2_and_inverse_pass':True})
        (b.ROOT/'transposition-checks.json').write_text(json.dumps(results,indent=2)+'\n')
if __name__=='__main__': unittest.main(verbosity=2)
