-- ============================================================================
-- PizzaCost Pro - Initial Database Schema Migration
-- Version: 001
-- Description: Complete database setup for Supabase
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- 1. EXISTING TABLES
-- ============================================================================

-- profiles
CREATE TABLE IF NOT EXISTS profiles (
    id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email           TEXT NOT NULL,
    nome_loja       TEXT,
    telefone        TEXT,
    subscription_status TEXT NOT NULL DEFAULT 'free'
        CHECK (subscription_status IN ('free', 'paid')),
    is_admin        BOOLEAN DEFAULT FALSE,  -- deprecated, use role instead
    role            TEXT NOT NULL DEFAULT 'user'
        CHECK (role IN ('user', 'admin', 'super_admin')),
    lgpd_consent_at     TIMESTAMPTZ,
    lgpd_consent_version TEXT,
    deleted_at          TIMESTAMPTZ,  -- soft delete
    subscription_expires_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- insumos (ingredients/supplies)
CREATE TABLE IF NOT EXISTS insumos (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    nome                TEXT NOT NULL,
    unidade             TEXT NOT NULL,
    preco               DECIMAL(10,2) NOT NULL CHECK (preco >= 0),
    quantidade_comprada DECIMAL(10,4) NOT NULL CHECK (quantidade_comprada > 0),
    custo_unitario      DECIMAL(10,6) NOT NULL CHECK (custo_unitario >= 0),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- tamanhos (pizza sizes)
CREATE TABLE IF NOT EXISTS tamanhos (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    nome                TEXT NOT NULL,
    custo_embalagem     DECIMAL(10,2) NOT NULL DEFAULT 0 CHECK (custo_embalagem >= 0),
    custo_massa         DECIMAL(10,2) NOT NULL DEFAULT 0 CHECK (custo_massa >= 0),
    preco_total         DECIMAL(10,2) NOT NULL DEFAULT 0 CHECK (preco_total >= 0),
    quantidade_embalagens INTEGER NOT NULL DEFAULT 1 CHECK (quantidade_embalagens > 0),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- bordas (pizza crusts/borders)
CREATE TABLE IF NOT EXISTS bordas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    nome            TEXT NOT NULL,
    tamanho_id      UUID NOT NULL REFERENCES tamanhos(id) ON DELETE CASCADE,
    preco_venda     DECIMAL(10,2) NOT NULL DEFAULT 0 CHECK (preco_venda >= 0),
    ingredientes    JSONB NOT NULL DEFAULT '[]',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- pizzas
CREATE TABLE IF NOT EXISTS pizzas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    nome            TEXT NOT NULL,
    tamanho_id      UUID NOT NULL REFERENCES tamanhos(id) ON DELETE CASCADE,
    border_id       UUID REFERENCES bordas(id) ON DELETE SET NULL,
    custo_adicionais DECIMAL(10,2) NOT NULL DEFAULT 0 CHECK (custo_adicionais >= 0),
    ingredientes    JSONB NOT NULL DEFAULT '[]',
    preco_venda     DECIMAL(10,2) NOT NULL DEFAULT 0 CHECK (preco_venda >= 0),
    custo_calculado DECIMAL(10,2) NOT NULL DEFAULT 0 CHECK (custo_calculado >= 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- combos
CREATE TABLE IF NOT EXISTS combos (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    nome                  TEXT NOT NULL,
    pizzas                JSONB NOT NULL DEFAULT '[]',
    outros_custos         DECIMAL(10,2) NOT NULL DEFAULT 0 CHECK (outros_custos >= 0),
    preco_venda_sugerido  DECIMAL(10,2) NOT NULL DEFAULT 0 CHECK (preco_venda_sugerido >= 0),
    custo_calculado       DECIMAL(10,2) NOT NULL DEFAULT 0 CHECK (custo_calculado >= 0),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for user-scoped lookups on core data tables
CREATE INDEX IF NOT EXISTS idx_insumos_user_id ON insumos (user_id);
CREATE INDEX IF NOT EXISTS idx_tamanhos_user_id ON tamanhos (user_id);
CREATE INDEX IF NOT EXISTS idx_bordas_user_id ON bordas (user_id);
CREATE INDEX IF NOT EXISTS idx_pizzas_user_id ON pizzas (user_id);
CREATE INDEX IF NOT EXISTS idx_combos_user_id ON combos (user_id);

-- ============================================================================
-- 2. NEW TABLES
-- ============================================================================

-- consent_logs (LGPD consent tracking)
CREATE TABLE IF NOT EXISTS consent_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    consent_type    TEXT NOT NULL,
    granted         BOOLEAN NOT NULL,
    ip_address      INET,
    user_agent      TEXT,
    policy_version  TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- audit_logs (system-wide audit trail)
CREATE TABLE IF NOT EXISTS audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES profiles(id) ON DELETE SET NULL,
    action          TEXT NOT NULL,
    resource        TEXT NOT NULL,
    resource_id     TEXT,
    old_data        JSONB,
    new_data        JSONB,
    ip_address      INET,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_created
    ON audit_logs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_resource_created
    ON audit_logs (resource, created_at DESC);

-- email_templates
CREATE TABLE IF NOT EXISTS email_templates (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug              TEXT NOT NULL UNIQUE,
    name              TEXT NOT NULL,
    subject_template  TEXT NOT NULL,
    body_html         TEXT NOT NULL,
    body_text         TEXT NOT NULL,
    variables_schema  JSONB NOT NULL DEFAULT '{}',
    language          TEXT NOT NULL DEFAULT 'pt-BR',
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- email_sequences
CREATE TABLE IF NOT EXISTS email_sequences (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    trigger_event   TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    steps           JSONB NOT NULL DEFAULT '[]',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- email_sends
CREATE TABLE IF NOT EXISTS email_sends (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    template_id         UUID REFERENCES email_templates(id) ON DELETE SET NULL,
    sequence_id         UUID REFERENCES email_sequences(id) ON DELETE SET NULL,
    step_index          INTEGER,
    subject             TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'sent', 'delivered', 'delayed', 'opened', 'clicked', 'bounced', 'complained', 'failed')),
    resend_message_id   TEXT,
    sent_at             TIMESTAMPTZ,
    opened_at           TIMESTAMPTZ,
    clicked_at          TIMESTAMPTZ,
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_email_sends_user_created
    ON email_sends (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_sends_status
    ON email_sends (status);

-- email_preferences
CREATE TABLE IF NOT EXISTS email_preferences (
    user_id                 UUID PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
    marketing_opt_in        BOOLEAN NOT NULL DEFAULT FALSE,
    transactional_enabled   BOOLEAN NOT NULL DEFAULT TRUE,
    unsubscribed_at         TIMESTAMPTZ,
    consent_date            TIMESTAMPTZ,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- payment_logs
CREATE TABLE IF NOT EXISTS payment_logs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    external_payment_id TEXT UNIQUE,
    provider            TEXT NOT NULL DEFAULT 'mercadopago',
    status              TEXT NOT NULL
        CHECK (status IN ('pending', 'approved', 'rejected', 'refunded', 'cancelled')),
    amount_brl          DECIMAL(10,2) NOT NULL CHECK (amount_brl >= 0),
    payment_method      TEXT,
    webhook_payload     JSONB,
    processed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payment_logs_user_created
    ON payment_logs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_payment_logs_status
    ON payment_logs (status);
CREATE INDEX IF NOT EXISTS idx_payment_logs_external_id
    ON payment_logs (external_payment_id);

-- subscription_history
CREATE TABLE IF NOT EXISTS subscription_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    old_status      TEXT NOT NULL,
    new_status      TEXT NOT NULL,
    changed_by      TEXT,
    reason          TEXT,
    payment_log_id  UUID REFERENCES payment_logs(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- system_settings (key-value config store)
CREATE TABLE IF NOT EXISTS system_settings (
    key             TEXT PRIMARY KEY,
    value           JSONB NOT NULL,
    updated_by      UUID REFERENCES profiles(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- lgpd_requests (data subject requests)
CREATE TABLE IF NOT EXISTS lgpd_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    type            TEXT NOT NULL
        CHECK (type IN ('data_export', 'account_deletion', 'rectification', 'portability')),
    status          TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    completed_at    TIMESTAMPTZ,
    download_url    TEXT,
    expires_at      TIMESTAMPTZ,
    processed_by    UUID REFERENCES profiles(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lgpd_requests_user_status
    ON lgpd_requests (user_id, status);
CREATE INDEX IF NOT EXISTS idx_lgpd_requests_status
    ON lgpd_requests (status);
CREATE INDEX IF NOT EXISTS idx_consent_logs_user_created
    ON consent_logs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_subscription_history_created
    ON subscription_history (created_at DESC);

-- user_activity (analytics / engagement tracking)
CREATE TABLE IF NOT EXISTS user_activity (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    action          TEXT NOT NULL,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_activity_user_created
    ON user_activity (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_activity_action
    ON user_activity (action);

-- ============================================================================
-- 3. ROW LEVEL SECURITY (RLS)
-- ============================================================================

-- Enable RLS on all user-scoped tables
ALTER TABLE insumos           ENABLE ROW LEVEL SECURITY;
ALTER TABLE tamanhos          ENABLE ROW LEVEL SECURITY;
ALTER TABLE bordas            ENABLE ROW LEVEL SECURITY;
ALTER TABLE pizzas            ENABLE ROW LEVEL SECURITY;
ALTER TABLE combos            ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_sends       ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_logs      ENABLE ROW LEVEL SECURITY;
ALTER TABLE consent_logs      ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_activity     ENABLE ROW LEVEL SECURITY;
ALTER TABLE lgpd_requests     ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles          ENABLE ROW LEVEL SECURITY;

-- profiles: users can read/update their own profile
CREATE POLICY profiles_select ON profiles
    FOR SELECT USING (auth.uid() = id);
CREATE POLICY profiles_update ON profiles
    FOR UPDATE USING (auth.uid() = id);
CREATE POLICY profiles_insert ON profiles
    FOR INSERT WITH CHECK (auth.uid() = id);

-- insumos
CREATE POLICY insumos_select ON insumos
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY insumos_insert ON insumos
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY insumos_update ON insumos
    FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY insumos_delete ON insumos
    FOR DELETE USING (auth.uid() = user_id);

-- tamanhos
CREATE POLICY tamanhos_select ON tamanhos
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY tamanhos_insert ON tamanhos
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY tamanhos_update ON tamanhos
    FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY tamanhos_delete ON tamanhos
    FOR DELETE USING (auth.uid() = user_id);

-- bordas
CREATE POLICY bordas_select ON bordas
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY bordas_insert ON bordas
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY bordas_update ON bordas
    FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY bordas_delete ON bordas
    FOR DELETE USING (auth.uid() = user_id);

-- pizzas
CREATE POLICY pizzas_select ON pizzas
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY pizzas_insert ON pizzas
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY pizzas_update ON pizzas
    FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY pizzas_delete ON pizzas
    FOR DELETE USING (auth.uid() = user_id);

-- combos
CREATE POLICY combos_select ON combos
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY combos_insert ON combos
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY combos_update ON combos
    FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY combos_delete ON combos
    FOR DELETE USING (auth.uid() = user_id);

-- email_sends
CREATE POLICY email_sends_select ON email_sends
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY email_sends_insert ON email_sends
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- email_preferences
CREATE POLICY email_preferences_select ON email_preferences
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY email_preferences_insert ON email_preferences
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY email_preferences_update ON email_preferences
    FOR UPDATE USING (auth.uid() = user_id);

-- payment_logs
CREATE POLICY payment_logs_select ON payment_logs
    FOR SELECT USING (auth.uid() = user_id);

-- consent_logs
CREATE POLICY consent_logs_select ON consent_logs
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY consent_logs_insert ON consent_logs
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- user_activity
CREATE POLICY user_activity_select ON user_activity
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY user_activity_insert ON user_activity
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- lgpd_requests
CREATE POLICY lgpd_requests_select ON lgpd_requests
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY lgpd_requests_insert ON lgpd_requests
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- ============================================================================
-- 4. SEED DATA - Email Templates
-- ============================================================================

INSERT INTO email_templates (slug, name, subject_template, body_html, body_text, variables_schema, language) VALUES

-- Welcome
('welcome', 'Boas-vindas', 'Bem-vindo ao PizzaCost Pro, {{nome_loja}}! 🍕',
'<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#ffffff;">
    <tr><td style="background:#DC2626;padding:32px;text-align:center;">
      <h1 style="color:#ffffff;margin:0;font-size:28px;">🍕 PizzaCost Pro</h1>
    </td></tr>
    <tr><td style="padding:32px;">
      <h2 style="color:#DC2626;margin-top:0;">Bem-vindo, {{nome_loja}}!</h2>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Estamos muito felizes em ter você conosco! O PizzaCost Pro vai te ajudar a calcular o custo real das suas pizzas e maximizar seus lucros.
      </p>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Para começar, siga estes passos simples:
      </p>
      <ol style="color:#374151;font-size:16px;line-height:1.8;">
        <li>Cadastre seus <strong>insumos</strong> (ingredientes e embalagens)</li>
        <li>Configure os <strong>tamanhos</strong> de pizza que você trabalha</li>
        <li>Monte suas <strong>pizzas</strong> e veja o custo calculado automaticamente</li>
      </ol>
      <div style="text-align:center;margin:32px 0;">
        <a href="{{app_url}}" style="background:#DC2626;color:#ffffff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">Começar Agora</a>
      </div>
      <p style="color:#6b7280;font-size:14px;">Se precisar de ajuda, responda este e-mail. Estamos aqui para você!</p>
    </td></tr>
    <tr><td style="background:#f3f4f6;padding:24px;text-align:center;">
      <p style="color:#9ca3af;font-size:12px;margin:0;">© PizzaCost Pro. Todos os direitos reservados.</p>
    </td></tr>
  </table>
</body>
</html>',
'Bem-vindo ao PizzaCost Pro, {{nome_loja}}!

Estamos muito felizes em ter você conosco! O PizzaCost Pro vai te ajudar a calcular o custo real das suas pizzas e maximizar seus lucros.

Para começar:
1. Cadastre seus insumos (ingredientes e embalagens)
2. Configure os tamanhos de pizza que você trabalha
3. Monte suas pizzas e veja o custo calculado automaticamente

Acesse: {{app_url}}

Se precisar de ajuda, responda este e-mail!
© PizzaCost Pro',
'{"nome_loja": "string", "app_url": "string"}',
'pt-BR'),

-- Password Reset
('password_reset', 'Redefinição de Senha', 'Redefinir sua senha - PizzaCost Pro',
'<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#ffffff;">
    <tr><td style="background:#DC2626;padding:32px;text-align:center;">
      <h1 style="color:#ffffff;margin:0;font-size:28px;">🍕 PizzaCost Pro</h1>
    </td></tr>
    <tr><td style="padding:32px;">
      <h2 style="color:#DC2626;margin-top:0;">Redefinir Senha</h2>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Recebemos uma solicitação para redefinir a senha da sua conta. Clique no botão abaixo para criar uma nova senha:
      </p>
      <div style="text-align:center;margin:32px 0;">
        <a href="{{reset_url}}" style="background:#DC2626;color:#ffffff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">Redefinir Senha</a>
      </div>
      <p style="color:#6b7280;font-size:14px;">Este link expira em 1 hora. Se você não solicitou a redefinição, ignore este e-mail.</p>
    </td></tr>
    <tr><td style="background:#f3f4f6;padding:24px;text-align:center;">
      <p style="color:#9ca3af;font-size:12px;margin:0;">© PizzaCost Pro. Todos os direitos reservados.</p>
    </td></tr>
  </table>
</body>
</html>',
'Redefinir Senha - PizzaCost Pro

Recebemos uma solicitação para redefinir a senha da sua conta.

Clique no link abaixo para criar uma nova senha:
{{reset_url}}

Este link expira em 1 hora. Se você não solicitou a redefinição, ignore este e-mail.

© PizzaCost Pro',
'{"reset_url": "string"}',
'pt-BR'),

-- Subscription Activated
('subscription_activated', 'Assinatura Ativada', 'Sua assinatura Pro foi ativada! 🎉',
'<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#ffffff;">
    <tr><td style="background:#DC2626;padding:32px;text-align:center;">
      <h1 style="color:#ffffff;margin:0;font-size:28px;">🍕 PizzaCost Pro</h1>
    </td></tr>
    <tr><td style="padding:32px;">
      <h2 style="color:#DC2626;margin-top:0;">Assinatura Pro Ativada! 🎉</h2>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Parabéns, {{nome_loja}}! Sua assinatura Pro foi ativada com sucesso.
      </p>
      <p style="color:#374151;font-size:16px;line-height:1.6;">Agora você tem acesso a:</p>
      <ul style="color:#374151;font-size:16px;line-height:1.8;">
        <li>Tamanhos de pizza <strong>ilimitados</strong></li>
        <li>Bordas <strong>ilimitadas</strong></li>
        <li>Pizzas <strong>ilimitadas</strong></li>
        <li>Criação de <strong>combos</strong></li>
        <li>Relatórios avançados</li>
      </ul>
      <p style="color:#6b7280;font-size:14px;">Validade: {{expires_at}}</p>
      <div style="text-align:center;margin:32px 0;">
        <a href="{{app_url}}" style="background:#DC2626;color:#ffffff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">Acessar Painel</a>
      </div>
    </td></tr>
    <tr><td style="background:#f3f4f6;padding:24px;text-align:center;">
      <p style="color:#9ca3af;font-size:12px;margin:0;">© PizzaCost Pro. Todos os direitos reservados.</p>
    </td></tr>
  </table>
</body>
</html>',
'Assinatura Pro Ativada!

Parabéns, {{nome_loja}}! Sua assinatura Pro foi ativada com sucesso.

Agora você tem acesso a:
- Tamanhos de pizza ilimitados
- Bordas ilimitadas
- Pizzas ilimitadas
- Criação de combos
- Relatórios avançados

Validade: {{expires_at}}

Acesse: {{app_url}}
© PizzaCost Pro',
'{"nome_loja": "string", "expires_at": "string", "app_url": "string"}',
'pt-BR'),

-- Subscription Expiring
('subscription_expiring', 'Assinatura Expirando', 'Sua assinatura Pro expira em {{days_remaining}} dias',
'<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#ffffff;">
    <tr><td style="background:#DC2626;padding:32px;text-align:center;">
      <h1 style="color:#ffffff;margin:0;font-size:28px;">🍕 PizzaCost Pro</h1>
    </td></tr>
    <tr><td style="padding:32px;">
      <h2 style="color:#DC2626;margin-top:0;">Sua assinatura expira em breve</h2>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Olá, {{nome_loja}}! Sua assinatura Pro expira em <strong>{{days_remaining}} dias</strong> ({{expires_at}}).
      </p>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Renove agora para continuar aproveitando todos os recursos sem interrupção.
      </p>
      <div style="text-align:center;margin:32px 0;">
        <a href="{{renew_url}}" style="background:#DC2626;color:#ffffff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">Renovar Assinatura</a>
      </div>
      <p style="color:#6b7280;font-size:14px;">Após o vencimento, sua conta voltará ao plano gratuito com limitações.</p>
    </td></tr>
    <tr><td style="background:#f3f4f6;padding:24px;text-align:center;">
      <p style="color:#9ca3af;font-size:12px;margin:0;">© PizzaCost Pro. Todos os direitos reservados.</p>
    </td></tr>
  </table>
</body>
</html>',
'Sua assinatura Pro expira em breve

Olá, {{nome_loja}}! Sua assinatura Pro expira em {{days_remaining}} dias ({{expires_at}}).

Renove agora para continuar aproveitando todos os recursos: {{renew_url}}

Após o vencimento, sua conta voltará ao plano gratuito com limitações.
© PizzaCost Pro',
'{"nome_loja": "string", "days_remaining": "number", "expires_at": "string", "renew_url": "string"}',
'pt-BR'),

-- Account Deletion
('account_deletion', 'Exclusão de Conta', 'Sua conta no PizzaCost Pro foi excluída',
'<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#ffffff;">
    <tr><td style="background:#DC2626;padding:32px;text-align:center;">
      <h1 style="color:#ffffff;margin:0;font-size:28px;">🍕 PizzaCost Pro</h1>
    </td></tr>
    <tr><td style="padding:32px;">
      <h2 style="color:#DC2626;margin-top:0;">Conta Excluída</h2>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Confirmamos que sua conta e todos os dados associados foram excluídos permanentemente do PizzaCost Pro, conforme solicitado.
      </p>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        De acordo com a LGPD, todos os seus dados pessoais foram removidos dos nossos sistemas.
      </p>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Sentiremos sua falta! Se quiser voltar no futuro, basta criar uma nova conta.
      </p>
      <p style="color:#6b7280;font-size:14px;">Se você não solicitou esta exclusão, entre em contato imediatamente respondendo este e-mail.</p>
    </td></tr>
    <tr><td style="background:#f3f4f6;padding:24px;text-align:center;">
      <p style="color:#9ca3af;font-size:12px;margin:0;">© PizzaCost Pro. Todos os direitos reservados.</p>
    </td></tr>
  </table>
</body>
</html>',
'Conta Excluída - PizzaCost Pro

Confirmamos que sua conta e todos os dados associados foram excluídos permanentemente, conforme solicitado.

De acordo com a LGPD, todos os seus dados pessoais foram removidos dos nossos sistemas.

Se você não solicitou esta exclusão, entre em contato imediatamente respondendo este e-mail.
© PizzaCost Pro',
'{}',
'pt-BR'),

-- Data Export Ready
('data_export_ready', 'Exportação de Dados Pronta', 'Seus dados estão prontos para download',
'<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#ffffff;">
    <tr><td style="background:#DC2626;padding:32px;text-align:center;">
      <h1 style="color:#ffffff;margin:0;font-size:28px;">🍕 PizzaCost Pro</h1>
    </td></tr>
    <tr><td style="padding:32px;">
      <h2 style="color:#DC2626;margin-top:0;">Dados Prontos para Download</h2>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Olá, {{nome_loja}}! Sua solicitação de exportação de dados (LGPD) foi processada com sucesso.
      </p>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        O link abaixo estará disponível por <strong>48 horas</strong>:
      </p>
      <div style="text-align:center;margin:32px 0;">
        <a href="{{download_url}}" style="background:#DC2626;color:#ffffff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">Baixar Meus Dados</a>
      </div>
      <p style="color:#6b7280;font-size:14px;">Expira em: {{expires_at}}</p>
    </td></tr>
    <tr><td style="background:#f3f4f6;padding:24px;text-align:center;">
      <p style="color:#9ca3af;font-size:12px;margin:0;">© PizzaCost Pro. Todos os direitos reservados.</p>
    </td></tr>
  </table>
</body>
</html>',
'Dados Prontos para Download - PizzaCost Pro

Olá, {{nome_loja}}! Sua solicitação de exportação de dados foi processada.

Baixar dados: {{download_url}}

O link estará disponível por 48 horas (expira em: {{expires_at}}).
© PizzaCost Pro',
'{"nome_loja": "string", "download_url": "string", "expires_at": "string"}',
'pt-BR'),

-- Onboarding Day 1
('onboarding_day1', 'Onboarding - Dia 1', 'Dica #1: Cadastre seus insumos no PizzaCost Pro',
'<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#ffffff;">
    <tr><td style="background:#DC2626;padding:32px;text-align:center;">
      <h1 style="color:#ffffff;margin:0;font-size:28px;">🍕 PizzaCost Pro</h1>
      <p style="color:#fecaca;margin:8px 0 0;font-size:14px;">Dica do Dia #1</p>
    </td></tr>
    <tr><td style="padding:32px;">
      <h2 style="color:#DC2626;margin-top:0;">Comece pelos Insumos!</h2>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Olá, {{nome_loja}}! O primeiro passo para calcular o custo correto das suas pizzas é cadastrar todos os seus insumos.
      </p>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        <strong>Dica:</strong> Cadastre os ingredientes com o preço que você realmente paga e a quantidade exata da embalagem. Assim o custo unitário será calculado automaticamente.
      </p>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Exemplos de insumos: mussarela (kg), molho de tomate (litro), farinha de trigo (kg), orégano (g).
      </p>
      <div style="text-align:center;margin:32px 0;">
        <a href="{{app_url}}/insumos" style="background:#DC2626;color:#ffffff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">Cadastrar Insumos</a>
      </div>
    </td></tr>
    <tr><td style="background:#f3f4f6;padding:24px;text-align:center;">
      <p style="color:#9ca3af;font-size:12px;margin:0;">© PizzaCost Pro. Todos os direitos reservados.</p>
    </td></tr>
  </table>
</body>
</html>',
'Dica #1: Comece pelos Insumos!

Olá, {{nome_loja}}! O primeiro passo para calcular o custo correto das suas pizzas é cadastrar todos os seus insumos.

Dica: Cadastre os ingredientes com o preço que você realmente paga e a quantidade exata da embalagem.

Exemplos: mussarela (kg), molho de tomate (litro), farinha de trigo (kg), orégano (g).

Cadastrar: {{app_url}}/insumos
© PizzaCost Pro',
'{"nome_loja": "string", "app_url": "string"}',
'pt-BR'),

-- Onboarding Day 3
('onboarding_day3', 'Onboarding - Dia 3', 'Dica #2: Configure tamanhos e bordas',
'<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#ffffff;">
    <tr><td style="background:#DC2626;padding:32px;text-align:center;">
      <h1 style="color:#ffffff;margin:0;font-size:28px;">🍕 PizzaCost Pro</h1>
      <p style="color:#fecaca;margin:8px 0 0;font-size:14px;">Dica do Dia #2</p>
    </td></tr>
    <tr><td style="padding:32px;">
      <h2 style="color:#DC2626;margin-top:0;">Configure Tamanhos e Bordas</h2>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Olá, {{nome_loja}}! Agora que seus insumos estão cadastrados, é hora de configurar os tamanhos de pizza e as bordas.
      </p>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        <strong>Tamanhos:</strong> Defina o custo da massa e da embalagem para cada tamanho (broto, média, grande, família).
      </p>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        <strong>Bordas:</strong> Configure bordas recheadas como catupiry, cheddar, chocolate. Inclua os ingredientes de cada borda para o cálculo correto.
      </p>
      <div style="text-align:center;margin:32px 0;">
        <a href="{{app_url}}/tamanhos" style="background:#DC2626;color:#ffffff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">Configurar Tamanhos</a>
      </div>
    </td></tr>
    <tr><td style="background:#f3f4f6;padding:24px;text-align:center;">
      <p style="color:#9ca3af;font-size:12px;margin:0;">© PizzaCost Pro. Todos os direitos reservados.</p>
    </td></tr>
  </table>
</body>
</html>',
'Dica #2: Configure Tamanhos e Bordas

Olá, {{nome_loja}}! Agora que seus insumos estão cadastrados, configure os tamanhos de pizza e as bordas.

Tamanhos: Defina o custo da massa e embalagem para cada tamanho.
Bordas: Configure bordas recheadas com seus ingredientes.

Configurar: {{app_url}}/tamanhos
© PizzaCost Pro',
'{"nome_loja": "string", "app_url": "string"}',
'pt-BR'),

-- Onboarding Day 7
('onboarding_day7', 'Onboarding - Dia 7', 'Dica #3: Monte suas pizzas e descubra o custo real!',
'<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#ffffff;">
    <tr><td style="background:#DC2626;padding:32px;text-align:center;">
      <h1 style="color:#ffffff;margin:0;font-size:28px;">🍕 PizzaCost Pro</h1>
      <p style="color:#fecaca;margin:8px 0 0;font-size:14px;">Dica do Dia #3</p>
    </td></tr>
    <tr><td style="padding:32px;">
      <h2 style="color:#DC2626;margin-top:0;">Monte suas Pizzas!</h2>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Olá, {{nome_loja}}! Chegou a hora mais esperada: montar suas pizzas e descobrir o custo real de cada uma.
      </p>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Selecione o tamanho, escolha uma borda (opcional), adicione os ingredientes e o PizzaCost Pro calcula tudo automaticamente. Você vai ver exatamente:
      </p>
      <ul style="color:#374151;font-size:16px;line-height:1.8;">
        <li>Custo total de cada pizza</li>
        <li>Margem de lucro por sabor</li>
        <li>Sugestão de preço de venda</li>
      </ul>
      <div style="text-align:center;margin:32px 0;">
        <a href="{{app_url}}/pizzas" style="background:#DC2626;color:#ffffff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">Montar Pizzas</a>
      </div>
    </td></tr>
    <tr><td style="background:#f3f4f6;padding:24px;text-align:center;">
      <p style="color:#9ca3af;font-size:12px;margin:0;">© PizzaCost Pro. Todos os direitos reservados.</p>
    </td></tr>
  </table>
</body>
</html>',
'Dica #3: Monte suas Pizzas!

Olá, {{nome_loja}}! Chegou a hora de montar suas pizzas e descobrir o custo real.

Selecione tamanho, borda e ingredientes. O PizzaCost Pro calcula:
- Custo total de cada pizza
- Margem de lucro por sabor
- Sugestão de preço de venda

Montar: {{app_url}}/pizzas
© PizzaCost Pro',
'{"nome_loja": "string", "app_url": "string"}',
'pt-BR'),

-- Reengagement
('reengagement', 'Reengajamento', 'Sentimos sua falta, {{nome_loja}}! 🍕',
'<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#ffffff;">
    <tr><td style="background:#DC2626;padding:32px;text-align:center;">
      <h1 style="color:#ffffff;margin:0;font-size:28px;">🍕 PizzaCost Pro</h1>
    </td></tr>
    <tr><td style="padding:32px;">
      <h2 style="color:#DC2626;margin-top:0;">Sentimos sua falta!</h2>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Olá, {{nome_loja}}! Faz um tempo que você não acessa o PizzaCost Pro. Seus ingredientes podem ter mudado de preço — que tal atualizar?
      </p>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Manter os custos atualizados é essencial para garantir que seus preços estejam corretos e que você não esteja perdendo dinheiro.
      </p>
      <div style="text-align:center;margin:32px 0;">
        <a href="{{app_url}}" style="background:#DC2626;color:#ffffff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">Voltar ao PizzaCost Pro</a>
      </div>
      <p style="color:#6b7280;font-size:14px;">Não quer mais receber estes e-mails? <a href="{{unsubscribe_url}}" style="color:#DC2626;">Cancelar inscrição</a></p>
    </td></tr>
    <tr><td style="background:#f3f4f6;padding:24px;text-align:center;">
      <p style="color:#9ca3af;font-size:12px;margin:0;">© PizzaCost Pro. Todos os direitos reservados.</p>
    </td></tr>
  </table>
</body>
</html>',
'Sentimos sua falta, {{nome_loja}}!

Faz um tempo que você não acessa o PizzaCost Pro. Seus ingredientes podem ter mudado de preço — que tal atualizar?

Acesse: {{app_url}}

Cancelar inscrição: {{unsubscribe_url}}
© PizzaCost Pro',
'{"nome_loja": "string", "app_url": "string", "unsubscribe_url": "string"}',
'pt-BR'),

-- Upgrade Nudge
('upgrade_nudge', 'Incentivo de Upgrade', 'Você atingiu o limite do plano gratuito',
'<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#ffffff;">
    <tr><td style="background:#DC2626;padding:32px;text-align:center;">
      <h1 style="color:#ffffff;margin:0;font-size:28px;">🍕 PizzaCost Pro</h1>
    </td></tr>
    <tr><td style="padding:32px;">
      <h2 style="color:#DC2626;margin-top:0;">Desbloqueie todo o potencial!</h2>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Olá, {{nome_loja}}! Você atingiu o limite do plano gratuito ({{limit_description}}).
      </p>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Com o plano <strong>Pro</strong>, você pode cadastrar tamanhos, bordas e pizzas ilimitadas, além de criar combos e acessar relatórios avançados.
      </p>
      <div style="background:#fef2f2;border-left:4px solid #DC2626;padding:16px;margin:24px 0;border-radius:0 8px 8px 0;">
        <p style="color:#DC2626;font-weight:bold;margin:0 0 8px;">Plano Pro</p>
        <p style="color:#374151;margin:0;font-size:20px;font-weight:bold;">R$ {{price}}/mês</p>
      </div>
      <div style="text-align:center;margin:32px 0;">
        <a href="{{upgrade_url}}" style="background:#DC2626;color:#ffffff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">Fazer Upgrade</a>
      </div>
    </td></tr>
    <tr><td style="background:#f3f4f6;padding:24px;text-align:center;">
      <p style="color:#9ca3af;font-size:12px;margin:0;">© PizzaCost Pro. Todos os direitos reservados.</p>
    </td></tr>
  </table>
</body>
</html>',
'Desbloqueie todo o potencial - PizzaCost Pro

Olá, {{nome_loja}}! Você atingiu o limite do plano gratuito ({{limit_description}}).

Com o plano Pro (R$ {{price}}/mês), você pode cadastrar tudo ilimitado e criar combos.

Fazer upgrade: {{upgrade_url}}
© PizzaCost Pro',
'{"nome_loja": "string", "limit_description": "string", "price": "string", "upgrade_url": "string"}',
'pt-BR'),

-- Churn Prevention
('churn_prevention', 'Prevenção de Churn', 'Sua assinatura Pro foi cancelada — sentiremos falta!',
'<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#ffffff;">
    <tr><td style="background:#DC2626;padding:32px;text-align:center;">
      <h1 style="color:#ffffff;margin:0;font-size:28px;">🍕 PizzaCost Pro</h1>
    </td></tr>
    <tr><td style="padding:32px;">
      <h2 style="color:#DC2626;margin-top:0;">Sentiremos falta do plano Pro!</h2>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Olá, {{nome_loja}}. Sua assinatura Pro foi cancelada e sua conta voltou ao plano gratuito.
      </p>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Seus dados continuam salvos, mas algumas funcionalidades ficaram limitadas:
      </p>
      <ul style="color:#374151;font-size:16px;line-height:1.8;">
        <li>Máximo de 1 tamanho e 1 borda</li>
        <li>Máximo de 3 pizzas</li>
        <li>Sem criação de combos</li>
      </ul>
      <p style="color:#374151;font-size:16px;line-height:1.6;">
        Mudou de ideia? Você pode reativar a qualquer momento:
      </p>
      <div style="text-align:center;margin:32px 0;">
        <a href="{{reactivate_url}}" style="background:#DC2626;color:#ffffff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">Reativar Pro</a>
      </div>
      <p style="color:#6b7280;font-size:14px;">Podemos ajudar? Responda este e-mail e conte como podemos melhorar.</p>
    </td></tr>
    <tr><td style="background:#f3f4f6;padding:24px;text-align:center;">
      <p style="color:#9ca3af;font-size:12px;margin:0;">© PizzaCost Pro. Todos os direitos reservados.</p>
    </td></tr>
  </table>
</body>
</html>',
'Sua assinatura Pro foi cancelada - PizzaCost Pro

Olá, {{nome_loja}}. Sua conta voltou ao plano gratuito.

Limitações: 1 tamanho, 1 borda, 3 pizzas, sem combos.

Mudou de ideia? Reativar: {{reactivate_url}}
© PizzaCost Pro',
'{"nome_loja": "string", "reactivate_url": "string"}',
'pt-BR');

-- ============================================================================
-- 5. SEED DATA - Email Sequences
-- ============================================================================

INSERT INTO email_sequences (name, trigger_event, is_active, steps) VALUES
('Onboarding', 'user_registered', TRUE,
 '[
   {"step_index": 0, "template_slug": "onboarding_day1", "delay_days": 1, "description": "Dia 1: Cadastrar insumos"},
   {"step_index": 1, "template_slug": "onboarding_day3", "delay_days": 3, "description": "Dia 3: Configurar tamanhos e bordas"},
   {"step_index": 2, "template_slug": "onboarding_day7", "delay_days": 7, "description": "Dia 7: Montar pizzas"}
 ]'::jsonb),
('Reengajamento', 'user_inactive', TRUE,
 '[
   {"step_index": 0, "template_slug": "reengagement", "delay_days": 14, "description": "14 dias inativo: e-mail de reengajamento"}
 ]'::jsonb);

-- ============================================================================
-- 6. SEED DATA - Admin Settings
-- ============================================================================

INSERT INTO system_settings (key, value, updated_at) VALUES
('plan_limits', '{
  "free": {
    "tamanhos": 1,
    "bordas": 1,
    "pizzas": 3,
    "combos": 0
  },
  "paid": {
    "tamanhos": 999,
    "bordas": 999,
    "pizzas": 999,
    "combos": 999
  }
}'::jsonb, NOW()),
('business_info', '{
  "name": "PizzaCost Pro",
  "support_email": "suporte@pizzacostpro.com.br",
  "website": "https://pizzacostpro.com.br",
  "primary_color": "#DC2626"
}'::jsonb, NOW()),
('email_sender_config', '{
  "from_name": "PizzaCost Pro",
  "from_email": "noreply@pizzacostpro.com.br",
  "reply_to": "suporte@pizzacostpro.com.br",
  "provider": "resend",
  "daily_limit": 500
}'::jsonb, NOW());

-- ============================================================================
-- Done! Migration 001 complete.
-- ============================================================================
