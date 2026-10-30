-- Yojak: Separate Zoho Authorizations from organization connections
-- Version : 004

-- 1. Create the Zoho Authorization table
CREATE TABLE zoho_authorizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    refresh_token_encrypted BYTEA NOT NULL,
    granted_scopes TEXT[] NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (
            status IN (
                'pending',
                'active',
                'revoked',
                'error'
            )
        ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

    -- Supports composite foreign keys that enforce tenant ownership
    UNIQUE (id, tenant_id)
);


-- 2. Index Authorization lookups by tenant
CREATE INDEX
idx_zoho_authorization_tenant_id
ON zoho_authorizations(tenant_id);


-- 3. Add a reference from each organization connection to its Zoho Authorization
ALTER TABLE merchant_connections
ADD COLUMN authorization_id UUID;


-- 4. Require every organization connection to referrence an existing organization
ALTER TABLE merchant_connections
ALTER COLUMN authorization_id SET NOT NULL;


-- 5. Add a Composite Unique constraint to support tenant-safe foreign key
ALTER TABLE merchant_connections
ADD CONSTRAINT merchant_connections_id_tenant_unique UIQUE (id, tenant_id);


-- 6. Ensure the referenced authorization belongs to the same tenant as the connection
ALTER TABLE merchant_connections
ADD CONSTRAINT merchant_connections_authorization_same_tenant_fk
FOREIGN KEY (authorization_id, tenant_id)
REFERENCES zoho_authorizations(id, tenant_id)
ON DELETE RESTRICT;


-- 7. Add a nullable pointerto the tenant's selected organization
ALTER TABLE tenants
ADD COLUMN active_organization_connection_id UUID;


-- 8. Ensure the selected organization connection belongs to the tenant referencing it 
ALTER TABLE tenants
ADD CONSTRAINT tenant_active_connection_same_tenant_fk
FOREIGN KEY (active_organization_connection_id, id)
REFERENCES merchant_connections(id, tenant_id) DEFERRABLE INITIALLY DEFERRED


-- 9. Remove old token fields from organization connections.
ALTER TABLE merchant_connections
DROP COLUMN refresh_token_encrypted

ALTER TABLE merchant_connections
DROP COLUMN granted_scopes