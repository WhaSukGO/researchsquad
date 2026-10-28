import json,sys
from pathlib import Path
from .music import inspect_prediction
try: result=inspect_prediction(sys.argv[1])
except Exception as e: result={'events':[],'chords':[],'parse_ok':False,'render_ok':False,'errors':[repr(e)]}
Path(sys.argv[2]).write_text(json.dumps(result,ensure_ascii=False,indent=2))
