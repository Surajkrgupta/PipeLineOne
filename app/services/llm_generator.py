"""Generates the solution explanation, code, and narration script for a DSA
problem. Supports two interchangeable backends:
  - "groq"   : hosted, free tier, fast, better quality
  - "ollama" : fully local, zero cost, needs Ollama running

Both are called through a single generate() function so the rest of the
pipeline doesn't care which one is active -- swap via LLM_PROVIDER in .env.
"""

import json
import re

import requests

from app.config import settings

SYSTEM_PROMPT_TEMPLATE = """You are an expert DSA (Data Structures & Algorithms) tutor \
creating content for a YouTube channel. You will be given a LeetCode problem. \
Respond ONLY with a single valid JSON object (no markdown fences, no preamble) \
with exactly these keys:

{{
  "approach_explanation": "2-4 sentence plain-English explanation of the approach/pattern used",
  "solution_code": "complete, correct, runnable Python solution with the standard LeetCode function signature",
  "time_complexity": "e.g. O(n)",
  "space_complexity": "e.g. O(1)",
  "narration_script": "a natural, spoken-style script (150-220 words) explaining the problem and approach for a voiceover, written to be read aloud, no code in this field"
}}

NARRATION STYLE REQUIREMENTS (important -- read carefully):
- Tone for this script: {tone}.
- Opening line style: {opening_style}
- Write like a real person talking, not like a textbook. Use contractions (it's, we're, let's), \
short sentences mixed with longer ones, and natural spoken rhythm.
- Avoid robotic/generic phrasing such as "In this video, we will discuss...", "Let's dive in", \
"Without further ado", or any line that sounds like it was copy-pasted across many videos.
- Vary sentence openings -- don't start consecutive sentences the same way.
- It's fine to include a brief rhetorical aside or personal-sounding observation \
("this one trips a lot of people up because...") -- that's what makes it sound human, not a script.

Be precise and correct -- this will be posted publicly. Double-check the code compiles logically \
and the complexity analysis is accurate before answering."""


class LLMGenerationError(Exception):
    pass


def _build_user_prompt(problem: dict) -> str:
    return (
        f"Problem title: {problem['title']}\n"
        f"Difficulty: {problem['difficulty']}\n"
        f"Topics: {', '.join(problem['topic_tags'])}\n\n"
        f"Problem statement (HTML):\n{problem['content_html']}\n\n"
        f"Example test cases:\n{problem['example_testcases']}"
    )


def _extract_json(raw_text: str) -> dict:
    """LLMs sometimes wrap JSON in markdown fences despite instructions -- strip those defensively."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw_text.strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)


def _call_groq(system_prompt: str, user_prompt: str) -> str:
    from groq import Groq
    import httpx

    # trust_env=False: some hosts (Render, etc.) inject HTTP_PROXY/HTTPS_PROXY
    # env vars for their own infra purposes. httpx respects these by default,
    # which can cause "APIConnectionError" when the proxy doesn't actually
    # handle this outbound traffic correctly. Disabling trust_env makes the
    # client connect directly, bypassing that ambient proxy config.
    http_client = httpx.Client(trust_env=False, timeout=60.0)
    client = Groq(api_key=settings.groq_api_key, http_client=http_client)
    completion = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.5,  # slightly higher than before -- helps narration sound less uniform week to week
    )
    return completion.choices[0].message.content


def _call_ollama(system_prompt: str, user_prompt: str) -> str:
    resp = requests.post(
        f"{settings.ollama_base_url}/api/chat",
        json={
            "model": settings.ollama_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.5},
        },
        timeout=180,  # local inference can be slow depending on hardware
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def generate_solution(
    problem: dict,
    narration_tone: str | None = None,
    opening_style: str | None = None,
    max_retries: int = 2,
) -> dict:
    """Returns dict with approach_explanation, solution_code, time_complexity,
    space_complexity, narration_script. Raises LLMGenerationError on failure.

    Retries transient failures (network hiccups, rate limits) up to
    max_retries times with a short backoff -- this runs once a day
    unattended, so it's worth a couple retries before giving up.

    narration_tone / opening_style are optional -- if not passed, they're
    picked automatically from variation_engine's weekly rotation."""
    from app.services import variation_engine

    narration_tone = narration_tone or variation_engine.get_weekly_narration_tone()
    opening_style = opening_style or variation_engine.get_weekly_opening_style()

    user_prompt = _build_user_prompt(problem)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(tone=narration_tone, opening_style=opening_style)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            if settings.llm_provider == "groq":
                raw = _call_groq(system_prompt, user_prompt)
            elif settings.llm_provider == "ollama":
                raw = _call_ollama(system_prompt, user_prompt)
            else:
                raise LLMGenerationError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")

            result = _extract_json(raw)

            required_keys = {"approach_explanation", "solution_code", "time_complexity",
                              "space_complexity", "narration_script"}
            if not required_keys.issubset(result.keys()):
                raise LLMGenerationError(f"LLM response missing keys: {required_keys - result.keys()}")

            return result

        except Exception as e:
            last_error = e
            # Groq's SDK wraps the real network error in a generic message
            # like "Connection error." -- print the full chain immediately so
            # Render's logs show the actual cause (DNS failure, TLS failure,
            # timeout, etc.) rather than just the unhelpful wrapper text.
            print(f"[llm_generator] attempt {attempt + 1} failed: {type(e).__name__}: {e}")
            if e.__cause__:
                print(f"[llm_generator] underlying cause: {type(e.__cause__).__name__}: {e.__cause__}")
            if attempt < max_retries:
                import time
                time.sleep(2 * (attempt + 1))  # short backoff: 2s, 4s
                continue

    cause_detail = f" | underlying cause: {type(last_error.__cause__).__name__}: {last_error.__cause__}" if last_error.__cause__ else ""
    raise LLMGenerationError(f"LLM generation failed after {max_retries + 1} attempts "
                              f"({type(last_error).__name__}): {last_error}{cause_detail}") from last_error