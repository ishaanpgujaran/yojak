-- Yojak Initial Database Schema
-- Version: 001

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Tenants
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    name TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Merchant Connections
CREATE TABLE merchant_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    provider TEXT NOT NULL CHECK (provider = 'zoho_inventory'),

    zoho_organization_id TEXT NOT NULL,

    refresh_token_encrypted BYTEA,

    granted_scopes TEXT[] NOT NULL DEFAULT '{}',

    status TEXT NOT NULL DEFAULT 'pending' 
        CHECK (
            status IN (
                'pending',
                'active',
                'revoked',
                'error'
            )
        ),
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (tenant_id, zoho_organization_id)
);


-- 3. MCP Client Authorizations
CREATE TABLE client_authorizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    connection_id UUID NOT NULL REFERENCES merchant_connections(id) ON DELETE CASCADE,

    client_id TEXT NOT NULL,

    scopes TEXT[] NOT NULL DEFAULT '{}',

    status TEXT NOT NULL DEFAULT 'active'
        CHECK (
            status IN (
                'active',
                'revoked'
            )
        ),
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (connection_id, client_id)
);


-- Indexes for Common Lookups
CREATE INDEX
idx_merchant_connections_tenant_id 
ON 
merchant_connections(tenant_id);

CREATE INDEX
idx_client_authorizations_tenant_id
ON
client_authorizations(tenant_id);

CREATE INDEX
idx_client_authorizations_connections_id
ON
client_authorizations(connection_id);

CREATE INDEX 
idx_client_authorizations_client_id
ON
client_authorizations(client_id);