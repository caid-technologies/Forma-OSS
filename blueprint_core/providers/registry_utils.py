from __future__ import annotations


def normalize_provider_name(value: str | None) -> str:
    provider = (value or "openai").strip().lower().replace("_", "-")
    aliases = {
        "base10": "baseten",
        "base-ten": "baseten",
        "baseten-model-apis": "baseten",
        "baseten-frontier": "baseten",
        "gmi-cloud": "gmi",
        "gmi_cloud": "gmi",
        "gmicloud": "gmi",
        "gemicloud": "gmi",
        "gmi-serving": "gmi",
    }
    return aliases.get(provider, provider or "openai")


def provider_slug(value: str | None) -> str:
    provider = normalize_provider_name(value)
    return "".join(char if char.isalnum() else "-" for char in provider).strip("-") or "provider"


def model_name_for_provider(provider_name: str | None, model: str | None) -> str:
    resolved_provider = normalize_provider_name(provider_name)
    resolved_model = (model or "").strip()
    prefixes = {f"{resolved_provider}/", f"{provider_slug(resolved_provider)}/"}
    if resolved_provider == "gmi":
        prefixes.update({"gmi-cloud/", "gmicloud/", "gemicloud/", "gmi-serving/"})
    for prefix in prefixes:
        if resolved_model.lower().startswith(prefix.lower()):
            resolved_model = resolved_model[len(prefix) :]
            break
    if resolved_provider == "gmi":
        aliases = {
            "fable": "anthropic/claude-fable-5",
            "fable-5": "anthropic/claude-fable-5",
            "claude-fable-5": "anthropic/claude-fable-5",
        }
        return aliases.get(resolved_model.lower(), resolved_model)
    return resolved_model
