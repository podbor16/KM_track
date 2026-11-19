-- leads.status was a legacy payment/refund marker. Refund is tracked by leads.refund.
-- Idempotent so it is safe to re-apply during staged deployments.
SET @ddl := IF(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'leads'
          AND column_name = 'status'
    ),
    'ALTER TABLE leads DROP COLUMN status',
    'SELECT 1'
);
PREPARE drop_leads_status_stmt FROM @ddl;
EXECUTE drop_leads_status_stmt;
DEALLOCATE PREPARE drop_leads_status_stmt;
