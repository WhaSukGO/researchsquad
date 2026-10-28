FROM python:3.12-slim@sha256:12316debbfb86890f6b2d825820612741ba527ad5a44e3902759141d572bfe8f
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /opt/base-requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes -r /opt/base-requirements.txt
RUN python -m pip install --no-cache-dir pillow==11.3.0 music21==9.9.2 converter21==4.0.1 verovio==6.3.0 rapidfuzz==3.14.1
RUN python -m pip freeze > /opt/python-lock.txt && dpkg-query -W > /opt/system-lock.txt
ENV PYTHONNOUSERSITE=1 PIP_NO_INDEX=1 PIP_REQUIRE_VIRTUALENV=1
ENV TMPDIR=/workspace/tmp
