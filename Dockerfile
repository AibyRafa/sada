# Sada - Live Demo image (Hugging Face Space with the Docker SDK, or any Docker host). CPU only.
# Same code, voiceprints, models and original recordings as the laptop.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PIP_NO_CACHE_DIR=1 PORT=7860 OMP_NUM_THREADS=2

COPY requirements-role4.txt requirements-role5.txt requirements-app.txt /tmp/req/
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r /tmp/req/requirements-role4.txt -r /tmp/req/requirements-role5.txt -r /tmp/req/requirements-app.txt \
 && pip install --no-deps resemblyzer

# Hugging Face runs the container as user 1000: the app folder must belong to it (Sada writes cache/ at start)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user
WORKDIR /home/user/app
COPY --chown=user . .

EXPOSE 7860
# The host sets PORT (Hugging Face: 7860). The models load in the background, about 30 s after start.
CMD ["python", "-m", "api.server"]
