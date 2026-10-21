"""Real-LLM backends (no dependencies): Ollama local server and any
OpenAI-compatible chat endpoint (OPENAI_API_KEY / OPENAI_BASE_URL env).

Also works with other OpenAI-compatible providers (LM Studio, vLLM,
Together, Groq) by setting OPENAI_BASE_URL + OPENAI_API_KEY.
"""
import json
import os
import re
import urllib.request

# matches revision ids like R-3-rev2, XA-rev1, EI-FRANCE_RESTORATION-rev2
REV_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_.-]{0,60}-rev\d+\b")

# models sometimes emit typographic hyphens (U+2010-2015, U+2212)
_HYPHENS = str.maketrans("‐‑‒–—―−", "-------")

SYSTEM = (
    "You are an auditing assistant. Answer the question using ONLY the "
    "admissible fragments below; every fragment IS admissible evidence "
    "and is tagged with its revision id in [brackets]. Answer concisely "
    "and cite the revision id(s) you relied on. Only if NO fragment is "
    "relevant to the question, answer exactly: insufficient evidence.")


def ollama_generate(model, prompt, base=None):
    base = base or os.environ.get("OLLAMA_HOST",
                                  "http://localhost:11434")
    req = urllib.request.Request(
        base + "/api/generate",
        data=json.dumps({"model": model, "prompt": prompt,
                         "stream": False}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["response"]


def openai_generate(model, prompt, base=None, api_key=None):
    base = (base or os.environ.get("OPENAI_BASE_URL",
                                   "https://api.openai.com/v1")).rstrip("/")
    key = api_key or os.environ["OPENAI_API_KEY"]
    body = {"model": model, "temperature": 0,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def make_generator(spec):
    """spec: 'ollama:llama3.1:8b' or 'openai:gpt-4o-mini'.
    Returns (callable(prompt)->text, model_id)."""
    backend, _, model = spec.partition(":")
    if backend == "ollama":
        return lambda p: ollama_generate(model, SYSTEM + "\n\n" + p), \
            f"ollama/{model}"
    if backend == "openai":
        return lambda p: openai_generate(model, p), f"openai/{model}"
    raise ValueError(f"unknown backend {backend}; use ollama:MODEL "
                     f"or openai:MODEL")


def cited_revs(text):
    """Revision ids cited in a model output."""
    return sorted(set(REV_RE.findall(text.translate(_HYPHENS))))
