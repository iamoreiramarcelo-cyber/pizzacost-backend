"""PizzaCost Pro - Pydantic models (request/response schemas).

All models are re-exported here for convenient imports:

    from app.models import LoginRequest, PizzaCreate, PaginatedResponse
"""

# common
from .common import (
    ErrorDetail,
    ErrorResponse,
    PaginatedResponse,
    PaginationMeta,
    PaginationParams,
    SuccessMessage,
    Unit,
)

# auth
from .auth import (
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    SignupRequest,
    TokenResponse,
)

# profile
from .profile import ProfileResponse, ProfileUpdate

# insumo
from .insumo import IngredienteItem, InsumoCreate, InsumoResponse, InsumoUpdate

# tamanho
from .tamanho import TamanhoCreate, TamanhoResponse, TamanhoUpdate

# borda
from .borda import BordaCreate, BordaResponse, BordaUpdate

# pizza
from .pizza import PizzaCreate, PizzaResponse, PizzaUpdate

# combo
from .combo import ComboPizzaItem, ComboCreate, ComboResponse, ComboUpdate

# subscription
from .subscription import (
    PlanLimits,
    SubscriptionActivateRequest,
    SubscriptionResponse,
    SubscriptionStatus,
)

# email
from .email import (
    EmailPreferencesUpdate,
    EmailSendResponse,
    EmailSequenceCreate,
    EmailSequenceResponse,
    EmailSequenceUpdate,
    EmailTemplateCreate,
    EmailTemplateResponse,
    EmailTemplateUpdate,
)

# admin
from .admin import (
    AdminDashboardResponse,
    AdminSettingsUpdate,
    AdminUserCreate,
    AdminUserListItem,
    AdminUserUpdate,
    AuditLogResponse,
    LgpdRequestResponse,
)

__all__ = [
    # common
    "Unit",
    "PaginationParams",
    "PaginationMeta",
    "PaginatedResponse",
    "ErrorDetail",
    "ErrorResponse",
    "SuccessMessage",
    # auth
    "LoginRequest",
    "SignupRequest",
    "TokenResponse",
    "PasswordResetRequest",
    "PasswordResetConfirm",
    # profile
    "ProfileResponse",
    "ProfileUpdate",
    # insumo
    "IngredienteItem",
    "InsumoCreate",
    "InsumoUpdate",
    "InsumoResponse",
    # tamanho
    "TamanhoCreate",
    "TamanhoUpdate",
    "TamanhoResponse",
    # borda
    "BordaCreate",
    "BordaUpdate",
    "BordaResponse",
    # pizza
    "PizzaCreate",
    "PizzaUpdate",
    "PizzaResponse",
    # combo
    "ComboPizzaItem",
    "ComboCreate",
    "ComboUpdate",
    "ComboResponse",
    # subscription
    "SubscriptionStatus",
    "PlanLimits",
    "SubscriptionResponse",
    "SubscriptionActivateRequest",
    # email
    "EmailTemplateCreate",
    "EmailTemplateUpdate",
    "EmailTemplateResponse",
    "EmailSequenceCreate",
    "EmailSequenceUpdate",
    "EmailSequenceResponse",
    "EmailSendResponse",
    "EmailPreferencesUpdate",
    # admin
    "AdminUserCreate",
    "AdminUserUpdate",
    "AdminDashboardResponse",
    "AdminUserListItem",
    "LgpdRequestResponse",
    "AuditLogResponse",
    "AdminSettingsUpdate",
]
