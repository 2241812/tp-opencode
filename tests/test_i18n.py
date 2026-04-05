from opencode_telegram_bot.utils.i18n import t, get_available_locales


def test_english_locale():
    assert t("welcome", locale="en") == "Welcome to OpenCode Telegram Bot! Send me a prompt to start coding."


def test_russian_locale():
    assert "Добро пожаловать" in t("welcome", locale="ru")


def test_chinese_locale():
    assert "欢迎" in t("welcome", locale="zh")


def test_german_locale():
    assert "Willkommen" in t("welcome", locale="de")


def test_spanish_locale():
    assert "Bienvenido" in t("welcome", locale="es")


def test_french_locale():
    assert "Bienvenue" in t("welcome", locale="fr")


def test_string_formatting():
    result = t("new_session", locale="en", session_id="abc123")
    assert "abc123" in result


def test_fallback_to_key():
    result = t("nonexistent_key_xyz", locale="en")
    assert result == "nonexistent_key_xyz"


def test_available_locales():
    locales = get_available_locales()
    assert "en" in locales
    assert "ru" in locales
    assert "zh" in locales
