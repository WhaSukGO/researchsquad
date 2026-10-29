"""Strict, snapshot-friendly agent definitions. No executable config imports."""
import json
import re
from pathlib import Path
from .sandbox import read_file
from .budgets import valid_limit

FIELDS={'version','id','model','reasoning_effort','system_prompt','tools','limits'}

def validate_agent(data):
    if not FIELDS <= set(data) or set(data)-FIELDS-{'checkpoint_interval'} or data['version']!=1:raise ValueError('Invalid agent definition fields/version')
    if 'checkpoint_interval' in data and (type(data['checkpoint_interval']) is not int or not 1 <= data['checkpoint_interval'] <= 1000):raise ValueError('checkpoint_interval must be 1..1000 actions; it is not an effort budget')
    if not isinstance(data['id'],str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}',data['id']):raise ValueError('Invalid agent id')
    if data['model'] is not None and (not isinstance(data['model'],str) or not data['model'].strip()):raise ValueError('Invalid model')
    if data['reasoning_effort'] not in {'low','medium','high'}:raise ValueError('Invalid reasoning effort')
    if not isinstance(data['system_prompt'],str) or not 1<=len(data['system_prompt'])<=32000:raise ValueError('Invalid system prompt')
    if not isinstance(data['tools'],list) or not data['tools'] or len(data['tools'])>64 or any(not isinstance(n,str) for n in data['tools']) or len(set(data['tools']))!=len(data['tools']):raise ValueError('Invalid tool grants')
    if set(data['limits'])!={'max_steps','max_seconds','command_timeout','model_call_timeout'} or any(not valid_limit(v) for v in data['limits'].values()):raise ValueError('Invalid limits')
    return data

def load_agent(path):
    path=Path(path)
    data=json.loads(path.read_text())
    validate_agent(data)
    data['system_prompt']=read_file(path.parent,data['system_prompt'],limit=32000).decode()
    return validate_agent(data)
