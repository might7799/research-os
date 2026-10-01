BEGIN;

ALTER TABLE searches ADD COLUMN IF NOT EXISTS workspace_id INTEGER;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS workspace_id INTEGER;
ALTER TABLE evidence ADD COLUMN IF NOT EXISTS workspace_id INTEGER;
ALTER TABLE claim_relations ADD COLUMN IF NOT EXISTS workspace_id INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'searches_user_id_fkey' AND conrelid = 'searches'::regclass) THEN
        ALTER TABLE searches ADD CONSTRAINT searches_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'searches_workspace_id_fkey' AND conrelid = 'searches'::regclass) THEN
        ALTER TABLE searches ADD CONSTRAINT searches_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES research_workspaces(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'claims_user_id_fkey' AND conrelid = 'claims'::regclass) THEN
        ALTER TABLE claims ADD CONSTRAINT claims_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'claims_workspace_id_fkey' AND conrelid = 'claims'::regclass) THEN
        ALTER TABLE claims ADD CONSTRAINT claims_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES research_workspaces(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'evidence_user_id_fkey' AND conrelid = 'evidence'::regclass) THEN
        ALTER TABLE evidence ADD CONSTRAINT evidence_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'evidence_workspace_id_fkey' AND conrelid = 'evidence'::regclass) THEN
        ALTER TABLE evidence ADD CONSTRAINT evidence_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES research_workspaces(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'claim_evidence_claim_id_fkey' AND conrelid = 'claim_evidence'::regclass) THEN
        ALTER TABLE claim_evidence ADD CONSTRAINT claim_evidence_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES claims(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'claim_evidence_evidence_id_fkey' AND conrelid = 'claim_evidence'::regclass) THEN
        ALTER TABLE claim_evidence ADD CONSTRAINT claim_evidence_evidence_id_fkey FOREIGN KEY (evidence_id) REFERENCES evidence(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'claim_relations_user_id_fkey' AND conrelid = 'claim_relations'::regclass) THEN
        ALTER TABLE claim_relations ADD CONSTRAINT claim_relations_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'claim_relations_source_claim_id_fkey' AND conrelid = 'claim_relations'::regclass) THEN
        ALTER TABLE claim_relations ADD CONSTRAINT claim_relations_source_claim_id_fkey FOREIGN KEY (source_claim_id) REFERENCES claims(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'claim_relations_target_claim_id_fkey' AND conrelid = 'claim_relations'::regclass) THEN
        ALTER TABLE claim_relations ADD CONSTRAINT claim_relations_target_claim_id_fkey FOREIGN KEY (target_claim_id) REFERENCES claims(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'claim_relations_workspace_id_fkey' AND conrelid = 'claim_relations'::regclass) THEN
        ALTER TABLE claim_relations ADD CONSTRAINT claim_relations_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES research_workspaces(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'research_workspaces_user_id_fkey' AND conrelid = 'research_workspaces'::regclass) THEN
        ALTER TABLE research_workspaces ADD CONSTRAINT research_workspaces_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id);
    END IF;
END $$;

COMMIT;
