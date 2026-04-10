from functools import lru_cache
from typing import Any

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str

    # Resend (Email)
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "PizzaCost Pro <noreply@pizzacostpro.com.br>"

    # MercadoPago
    MERCADOPAGO_ACCESS_TOKEN: str = ""
    MERCADOPAGO_WEBHOOK_SECRET: str = ""

    # Asaas
    ASAAS_API_KEY: str = ""

    # OpenAI
    OPENAI_API_KEY: str = ""

    # Application
    APP_URL: str = "http://localhost:3000"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,https://calculo-de-pizza-main.vercel.app"
    ENVIRONMENT: str = "dev"
    API_RATE_LIMIT: str = "100/minute"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "prod"

    PLAN_LIMITS: dict[str, Any] = {
        "free": {
            "max_pizzas": 5,
            "max_ingredients": 999,
            "max_tamanhos": 2,
            "max_bordas": 0,
            "max_combos": 0,
            "max_calculator_uses": 5,
            "can_export_pdf": False,
            "can_use_ai": False,
            "can_multi_tenant": False,
        },
        "paid": {
            "max_pizzas": 999,
            "max_ingredients": 999,
            "max_tamanhos": 999,
            "max_bordas": 999,
            "max_combos": 999,
            "max_calculator_uses": 999,
            "can_export_pdf": True,
            "can_use_ai": True,
            "can_multi_tenant": True,
        },
    }

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
