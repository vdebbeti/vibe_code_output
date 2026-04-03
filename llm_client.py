"""
Unified LLM client supporting OpenAI, Google Gemini, and Anthropic Claude.
All functions return plain response text.
"""
import base64

# ── Provider metadata (used by app.py sidebar) ────────────────────────────────
PROVIDER_MODELS: dict[str, list[str]] = {
    "OpenAI":           ["gpt-4o", "gpt-4o-mini"],
    "Google Gemini":    ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
    "Anthropic Claude": ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5-20251001"],
}

PROVIDER_KEY_LABELS: dict[str, str] = {
    "OpenAI":           "OpenAI API Key",
    "Google Gemini":    "Google AI API Key",
    "Anthropic Claude": "Anthropic API Key",
}

PROVIDER_KEY_PLACEHOLDERS: dict[str, str] = {
    "OpenAI":           "sk-... or sk-proj-...",
    "Google Gemini":    "AIza...",
    "Anthropic Claude": "sk-ant-...",
}

PROVIDER_KEY_HELP: dict[str, str] = {
    "OpenAI": (
        "Get your key at platform.openai.com → API keys. "
        "Both `sk-` and `sk-proj-` keys work. "
        "If you see 'invalid_api_key', re-copy carefully — trailing periods or spaces break the key."
    ),
    "Google Gemini": "Get your key at aistudio.google.com → Get API key.",
    "Anthropic Claude": "Get your key at console.anthropic.com → API Keys.",
}


# ── Unified entry point ───────────────────────────────────────────────────────
def call_llm(
    system: str,
    user: str,
    provider: str,
    model: str,
    api_key: str,
    image_bytes: bytes | None = None,
    image_mime: str = "image/png",
    max_tokens: int = 2000,
) -> str:
    """Call any supported LLM. Returns the response text."""
    if provider == "OpenAI":
        return _call_openai(system, user, model, api_key, image_bytes, image_mime, max_tokens)
    elif provider == "Google Gemini":
        return _call_gemini(system, user, model, api_key, image_bytes, image_mime, max_tokens)
    elif provider == "Anthropic Claude":
        return _call_claude(system, user, model, api_key, image_bytes, image_mime, max_tokens)
    else:
        raise ValueError(f"Unknown provider: {provider!r}")


# ── OpenAI ────────────────────────────────────────────────────────────────────
def _call_openai(system, user, model, api_key, image_bytes, image_mime, max_tokens):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode()
        user_content: list = [
            {"type": "image_url", "image_url": {"url": f"data:{image_mime};base64,{b64}", "detail": "high"}},
            {"type": "text", "text": user},
        ]
    else:
        user_content = user  # plain string is fine for text-only calls

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user_content},
        ],
        max_tokens=max_tokens,
        temperature=0,
    )
    return resp.choices[0].message.content.strip()


# ── Google Gemini ─────────────────────────────────────────────────────────────
def _call_gemini(system, user, model, api_key, image_bytes, image_mime, max_tokens):
    import google.generativeai as genai
    genai.configure(api_key=api_key)

    generation_config = genai.GenerationConfig(max_output_tokens=max_tokens, temperature=0.0)
    gemini_model = genai.GenerativeModel(
        model_name=model,
        system_instruction=system,
        generation_config=generation_config,
    )

    parts: list = []
    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode()
        parts.append({"inline_data": {"mime_type": image_mime, "data": b64}})
    parts.append(user)

    resp = gemini_model.generate_content(parts)
    return resp.text.strip()


# ── Anthropic Claude ──────────────────────────────────────────────────────────
def _call_claude(system, user, model, api_key, image_bytes, image_mime, max_tokens):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    user_content: list = []
    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode()
        user_content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": image_mime, "data": b64},
        })
    user_content.append({"type": "text", "text": user})

    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    return resp.content[0].text.strip()
