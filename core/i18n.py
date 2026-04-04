"""
ApexFlash Multi-Language Engine (v3.20.0)
────────────────────────────────────────────────────────
Supported: English (en), Spanish (es), Chinese (zh), Dutch (nl)
"""

LOCALES = {
    "en": {
        "WELCOME": "🚀 *Welcome to ApexFlash Godmode Infinity v3.20.0*\n\nSolana's most advanced autonomous trading terminal.",
        "MAIN_MENU": "⚡ *MAIN MENU*",
        "AFFILIATE": "Affiliate Program",
        "PREMIUM": "Premium",
        "TRADE": "Trade",
        "ADVISOR": "AI Coach",
        "LANGUAGE": "Language",
        "SELECT_LANG": "Select your language:",
    },
    "es": {
        "WELCOME": "🚀 *Bienvenido a ApexFlash Godmode Infinity v3.20.0*\n\nLa terminal de trading autónomo más avanzada de Solana.",
        "MAIN_MENU": "⚡ *MENÚ PRINCIPAL*",
        "AFFILIATE": "Programa de Afiliados",
        "PREMIUM": "Premium",
        "TRADE": "Operar",
        "ADVISOR": "Asesor AI",
        "LANGUAGE": "Idioma",
        "SELECT_LANG": "Seleccione su idioma:",
    },
    "zh": {
        "WELCOME": "🚀 *欢迎使用 ApexFlash 极速战意 v3.20.0*\n\nSolana 最先进的自主交易终端。",
        "MAIN_MENU": "⚡ *主菜单*",
        "AFFILIATE": "联盟计划",
        "PREMIUM": "高级版",
        "TRADE": "交易",
        "ADVISOR": "AI 辅导",
        "LANGUAGE": "语言",
        "SELECT_LANG": "选择您的语言:",
    },
    "nl": {
        "WELCOME": "🚀 *Welkom bij ApexFlash Godmode Infinity v3.20.0*\n\nSolana's meest geavanceerde autonome trading terminal.",
        "MAIN_MENU": "⚡ *HOOFDMENU*",
        "AFFILIATE": "Affiliate Programma",
        "PREMIUM": "Premium",
        "TRADE": "Handelen",
        "ADVISOR": "AI Coach",
        "LANGUAGE": "Taal",
        "SELECT_LANG": "Selecteer je taal:",
    }
}

def get_text(key: str, lang: str = "en") -> str:
    """Get localized text by key and language code."""
    locale = LOCALES.get(lang, LOCALES["en"])
    return locale.get(key, LOCALES["en"].get(key, key))
