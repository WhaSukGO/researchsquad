FROM python:3.12-slim@sha256:12316debbfb86890f6b2d825820612741ba527ad5a44e3902759141d572bfe8f
RUN python -m pip install --no-cache-dir pypdf==6.21.4
RUN python -c "from pypdf import PdfReader; import pypdf; assert pypdf.__version__ == '6.21.4'"
