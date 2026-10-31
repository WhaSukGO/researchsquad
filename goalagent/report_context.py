"""Resolve report references only against explicitly delivered material."""


def report_targets(team,assignment):
    result=[]
    inputs=assignment.get('inputs',{})
    if isinstance(inputs,dict):
        result.extend({'id':v['artifact_id'],'path':v['path']} for v in inputs.values())
    else:
        result.extend({'id':team.public_inputs[n],'path':'inputs/'+n} for n in inputs if n in team.public_inputs)
    result.extend({'id':aid,'path':'inputs/parent/'+team.state['artifacts'][aid]['path']}
                  for aid in assignment.get('parent_artifacts',[]))
    if assignment.get('review_of'):result.append({'id':assignment['review_of'],'path':None})
    if assignment.get('task_id'):result.append({'id':assignment['task_id'],'path':None})
    return result


def resolve_objections(team,report,assignment):
    aliases={r['path']:r['id'] for r in report_targets(team,assignment) if r['path']}
    resolutions=[]
    for objection in report.get('objections',[]):
        target=objection.get('target_id')
        if not isinstance(target,str):continue
        matches=[path for path in aliases if target==path or target.startswith(path+':')]
        if matches:
            path=max(matches,key=len);canonical=aliases[path]
            objection['target_id']=canonical
            resolutions.append({'supplied':target,'artifact_id':canonical,'scope':'Delivered path alias only; statement/evidence unchanged'})
    return resolutions


def check_image_capability(config,files):
    if 'view_image' in config['tools'] or 'run' in config['tools']:return
    for path,raw in files:
        image=raw.startswith((b'\x89PNG',b'\xff\xd8\xff',b'GIF87a',b'GIF89a')) or (raw.startswith(b'RIFF') and raw[8:12]==b'WEBP')
        if image:raise ValueError(f'Input capability mismatch: {path} is an image, but {config["id"]} has no view_image or execution grant. Configure a fresh assignment with an explicit permitted reader; no tool was auto-granted.')
