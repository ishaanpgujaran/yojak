-- Yojak: Add inactive status and enforce one active connection per tenant & authorization
-- Version: 006

-- Allow previously selected connections to have an inactive status
ALTER TABLE merchant_connections 
DROP CONSTRAINT merchant_connections_status_check;

ALTER TABLE merchant_connections
ADD CONSTRAINT merchant_connections_status_check
CHECK (
    status IN ('pending', 'active', 'inactive', 'revoked', 'error')
);


-- Enforce at most one active organization connection per tenant & authorization
CREATE UNIQUE INDEX one_active_connection_per_tenant
ON merchant_connections (tenant_id)
WHERE status = 'active';
