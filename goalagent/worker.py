"""Music worker compatibility adapter over the configurable Agent runtime."""
from pathlib import Path
from .agent import Agent
from .sandbox import DockerSandbox
from .configuration import load_agent
from .toolkit import default_registry

ROOT=Path(__file__).resolve().parents[1]
WORKER_INSTRUCTIONS=(ROOT/'agents/music/experiment.md').read_text()
MANAGED_INSTRUCTIONS=(ROOT/'agents/music/managed.md').read_text()

class ExperimentWorker(Agent):
    def __init__(self, folder, assignment, provider, policy, sandbox_factory=DockerSandbox):
        config=load_agent(ROOT/'agents/music/experiment.json')
        instructions=config['system_prompt']
        if policy.get('managed_environment'):
            start=instructions.index('You are not restricted')
            end=instructions.index('Return one JSON action.')
            instructions=instructions[:start]+('Implement new recognition approaches by writing and executing scripts in a prepared isolated container. Use only host tools, not tools inside the model process.\n')+instructions[end:]
            instructions=instructions.replace('dependency installation, training and inference','experiment execution and inference')+MANAGED_INSTRUCTIONS
        config['system_prompt']=instructions
        super().__init__(folder,assignment,provider,policy,config,default_registry(),sandbox_factory)
