FROM python:3.12-slim@sha256:12316debbfb86890f6b2d825820612741ba527ad5a44e3902759141d572bfe8f
RUN python -m pip install --no-cache-dir torch==2.9.1 --index-url https://download.pytorch.org/whl/cu128
RUN python -m pip install --no-cache-dir numpy==2.2.6 safetensors==0.6.2 packaging==25.0
RUN python -c "import torch, numpy, safetensors.torch; x=torch.ones(2,requires_grad=True); x.sum().backward(); assert x.grad is not None"
RUN python -m pip freeze > /opt/training-lock.txt
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
