from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.models.administration import ConfigurationVariable

RESERVED = {"APIKEY_GEMINI", "APIKEY_OPENAI", "USAR_GEMINI", "GEMINI_MODEL", "OPENAI_MODEL"}


def is_secret(name):
    return any(part in name for part in ("APIKEY", "API_KEY", "SECRET", "PASSWORD", "TOKEN"))


def seed_configuration(session, settings):
    defaults = {"APIKEY_GEMINI": settings.gemini_api_key.get_secret_value(),
                "APIKEY_OPENAI": settings.openai_api_key.get_secret_value(),
                "USAR_GEMINI": "true", "GEMINI_MODEL": settings.gemini_model,
                "OPENAI_MODEL": settings.openai_model}
    for name, value in defaults.items():
        session.execute(insert(ConfigurationVariable).values(name=name, value=value).on_conflict_do_nothing())
    session.flush()


def provider_settings(session, settings):
    seed_configuration(session, settings)
    values = dict(session.execute(select(ConfigurationVariable.name, ConfigurationVariable.value)).all())
    session.commit()
    return settings.model_copy(update={"gemini_api_key": SecretStr(values['APIKEY_GEMINI']),
        "openai_api_key": SecretStr(values['APIKEY_OPENAI']),
        "gemini_model": values['GEMINI_MODEL'], "openai_model": values['OPENAI_MODEL']}), values['USAR_GEMINI'] == 'true'
