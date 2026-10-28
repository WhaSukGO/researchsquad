from goalagent.provider import CodexProvider
schema={'type':'object','properties':{'ready':{'type':'boolean'}},'required':['ready'],'additionalProperties':False}
result,meta=CodexProvider().call('Return ready=true. Do not use tools.',schema,'runs/agent-probe/call',timeout=120)
print(result,meta)
