-- Yojak: Enforce one Zoho authorization per tenant
-- Version: 000

ALTER TABLE zoho_authorizations
ADD CONSTRAINT zoho_authorizations_tenant_id_unique UNIQUE (tenant_id);