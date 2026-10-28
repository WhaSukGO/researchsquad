from fractions import Fraction
import music21 as m21
from scorebench.metrics import (chord_from_label, events_from_score, kern_melody_only,
                               parse_events, reference_chords, restore_kern_body,
                               sequence_metrics, transpose_reference_dialect, xml_chords)

SCORE = '**kern\t**mxhm\n*clefG2\t*\n*k[]\t*\n*M4/4\t*\n=\t=\n2e\tG:maj/B\n2g\tD:maj/F#\n==\t==\n*-\t*-\n'


def test_reference_chords_not_silently_dropped():
    assert reference_chords(SCORE) == [('G', 'major', 'B', ()), ('D', 'major', 'F#', ())]


def test_slash_bass_and_melody_transpose():
    result = transpose_reference_dialect(SCORE, 'M2')
    assert '2f#\tA:maj/C#' in result
    assert '2a\tE:maj/G#' in result
    assert '*k[f#c#]' in result


def test_flat_chord_and_quality_preserved():
    source = SCORE.replace('G:maj/B', 'F:min/Ab')
    result = transpose_reference_dialect(source, 'M2')
    assert 'G:min/Bb' in result


def test_chord_extensions_and_bass_count_as_errors():
    ref = [chord_from_label('G:7/B')]
    pred = [chord_from_label('G:maj/D')]
    assert sequence_metrics(ref, pred)['substitutions'] == 1


def test_wrong_duration_counts_even_with_correct_pitch():
    result = sequence_metrics([(('C4',), '1')], [(('C4',), '2')])
    assert result['f1'] == 0


def test_empty_prediction_counts_every_reference_event():
    result = sequence_metrics([1, 2, 3], [])
    assert result['deletions'] == 3 and result['recall'] == 0


def test_extra_notes_penalized_and_rate_can_exceed_one():
    result = sequence_metrics([1], [2, 3, 4])
    assert result['errors'] == 3 and result['error_rate'] == 3


def test_ties_only_merge_matching_pitches():
    s = m21.stream.Score();p = m21.stream.Part()
    a = m21.note.Note('C4', quarterLength=1);a.tie = m21.tie.Tie('start')
    b = m21.note.Note('D4', quarterLength=1);b.tie = m21.tie.Tie('stop')
    p.append([a,b]);s.append(p)
    assert len(events_from_score(s)) == 2
    b.pitch = m21.pitch.Pitch('C4')
    assert events_from_score(s) == [(('C4',), '2')]


def test_no_text_format_penalty_for_beams_or_bar_numbers():
    a = '**kern\n*clefG2\n*k[]\n*M4/4\n=1\n8cL\n8dJ\n*-\n'
    b = a.replace('=1','=').replace('8cL','8c').replace('8dJ','8d')
    assert parse_events(a,'humdrum')[0] == parse_events(b,'humdrum')[0]


def test_header_restoration_does_not_correct_notes():
    assert restore_kern_body('*clefG2\n8c\n8d') == '**kern\n*clefG2\n8c\n8d\n*-\n'


def test_xml_harmony_does_not_confuse_words_with_chords():
    xml = '<score-partwise><part><measure><direction><words>G7</words></direction><harmony><root><root-step>D</root-step></root><kind>major</kind><degree><degree-value>9</degree-value><degree-alter>0</degree-alter><degree-type>add</degree-type></degree></harmony></measure></part></score-partwise>'
    assert xml_chords(xml) == [chord_from_label('D:add9')]


def test_known_pitch_and_duration_reference():
    assert parse_events(kern_melody_only(SCORE),'humdrum')[0] == [(('E4',),'2'),(('G4',),'2')]
