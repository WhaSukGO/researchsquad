"""Host-registered evaluators. New domains add adapters, never agent-authored scoring."""
import json
from dataclasses import dataclass

@dataclass(frozen=True)
class Evaluator:
    version: str
    evaluate: object
    def __call__(self, snapshot, task):return self.evaluate(snapshot, task)


def sorted_numbers(snapshot,task):
    """Non-music fixture for verifying delegation, artifacts and protected scoring."""
    expected=sorted(json.loads(task['inputs']['numbers.json']))
    try:actual=json.loads(snapshot['result.json'])
    except (KeyError,ValueError):return {'accepted':False,'exact_match':False,'reason':'Missing/invalid result.json'}
    return {'accepted':actual==expected,'exact_match':actual==expected,'samples':len(expected),
            'scope':'Software integration fixture; not research quality or generalization.'}

EVALUATORS={'sorted_numbers':Evaluator('sorted-numbers-v1',sorted_numbers)}
