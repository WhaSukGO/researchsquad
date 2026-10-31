"""Assignment-local observations; no cross-run or peer-review memory."""
import json


def observed_work(history):
    reads={};receipts=[];images=[]
    for action in history:
        observation=action.get('observation',{})
        if not isinstance(observation,dict) or 'error' in observation:continue
        eid=action.get('evidence_id')
        if action.get('tool')=='write_file':reads.pop(observation.get('written'),None)
        if action.get('tool')=='read_file' and 'text' in observation:
            arg=json.loads(action['argument']);path=arg['path'];revision=observation.get('content_id')
            record=reads.get(path)
            if record is None or record['content_id']!=revision:
                record={'path':path,'content_id':revision,'total_bytes':observation['bytes'],'windows':[]}
                reads[path]=record
            record['windows'].append({'offset':observation.get('offset',0),
                'end_offset':observation.get('end_offset',observation.get('offset',0)+len(observation['text'].encode())),
                'evidence_id':eid,'step':action.get('step')})
        if action.get('tool')=='read_evidence':
            arg=json.loads(action['argument']);receipts.append({'id':arg['id'],'offset':arg.get('offset',0),'evidence_id':eid})
        if action.get('tool')=='view_image':images.append({'path':action['argument'],'evidence_id':eid})
    return {'scope':'Actual observations by this assignment, not proof of comprehension; recheck after files change',
        'read_files':list(reads.values())[-64:],'read_receipts':receipts[-64:],'viewed_images':images[-32:],
        'omitted_files':max(0,len(reads)-64),'omitted_receipt_reads':max(0,len(receipts)-64)}
