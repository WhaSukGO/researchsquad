import json
import pytest
from goalagent import netlang

I16={'op':'input','h':16,'w':16}
NET1={'layers':[I16,{'op':'output','n':10}]}
NET2={'layers':[I16,{'op':'full','n':12},{'op':'output','n':10}]}
NET5={'layers':[I16,{'op':'local','k':3,'stride':2,'n':2},{'op':'tie'},{'op':'local','k':5,'stride':2,'n':4},{'op':'tie'},{'op':'output','n':10}]}
LENET1={'layers':[I16,{'op':'local','k':5,'stride':2,'n':12},{'op':'tie'},{'op':'local','k':5,'stride':2,'n':12,'fan_in':8},{'op':'tie'},{'op':'full','n':30},{'op':'output','n':10}]}


def test_counts_match_lecun_1989_toronto_report():
    assert (netlang.analyze(NET1)['connections'],netlang.analyze(NET1)['params'])==(2570,2570)
    assert (netlang.analyze(NET2)['connections'],netlang.analyze(NET2)['params'])==(3214,3214)
    a=netlang.analyze(NET5);assert (a['connections'],a['params'],a['tied_layers'])==(5194,1060,2)
    assert [l['shape'] for l in a['layers'] if 'shape' in l]==[[1,16,16],[2,8,8],[4,4,4],[10,1,1]]


def test_counts_match_lecun_1989_neural_computation_zip_code_net():
    a=netlang.analyze(LENET1);assert (a['connections'],a['params'])==(64660,9760)
    assert abs(netlang.eta_days(64660,7291,23)-3.0)<1e-9


def test_untied_local_costs_as_many_parameters_as_connections():
    untied={'layers':[I16,{'op':'local','k':3,'stride':2,'n':2},{'op':'output','n':10}]}
    a=netlang.analyze(untied);assert a['params']==a['connections'] and a['tied_layers']==0


def test_vocabulary_has_no_convolution_and_macro_is_locked_until_unlocked():
    with pytest.raises(ValueError):netlang.analyze({'layers':[I16,{'op':'conv','k':5,'n':4},{'op':'output','n':10}]})
    macro={'layers':[I16,{'op':'shared_map','k':3,'stride':2,'n':2},{'op':'output','n':10}]}
    with pytest.raises(ValueError,match='not in your vocabulary'):netlang.analyze(macro)
    a=netlang.analyze(macro,macros=('shared_map',));assert a['tied_layers']==1 and a['params']==(2*9+2*64)+10*(2*64+1)


def test_tie_must_follow_untied_local_and_avg_needs_divisible_input():
    with pytest.raises(ValueError):netlang.analyze({'layers':[I16,{'op':'tie'},{'op':'output','n':10}]})
    with pytest.raises(ValueError):netlang.analyze({'layers':[I16,{'op':'local','k':3,'stride':2,'n':2},{'op':'tie'},{'op':'tie'},{'op':'output','n':10}]})
    with pytest.raises(ValueError):netlang.analyze({'layers':[I16,{'op':'avg','k':3},{'op':'output','n':10}]})
    a=netlang.analyze({'layers':[I16,{'op':'avg','k':2},{'op':'output','n':10}]});assert a['params']==10*65 and a['layers'][1]['fixed']


def test_canonical_is_stable_and_json_input_accepted():
    assert netlang.canonical(NET5)==netlang.canonical(json.dumps(NET5))
    assert json.loads(netlang.canonical(NET5))['layers'][1]['op']=='local'
