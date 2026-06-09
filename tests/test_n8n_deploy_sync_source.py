import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_JSON = ROOT / "package.json"
SYNC_SCRIPT = ROOT / "scripts" / "sync-n8n-workflow.mjs"
POST_DEPLOY_HOOK = ROOT / "scripts" / "vps-post-deploy.sh"
INSTALL_HOOK = ROOT / "scripts" / "install-vps-post-merge-hook.sh"
ENV_EXAMPLE = ROOT / ".env.example"


def test_package_installs_workflow_sdk_for_deploy_sync():
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))

    assert package["scripts"]["sync:n8n"] == "node scripts/sync-n8n-workflow.mjs"
    assert package["dependencies"]["@n8n/workflow-sdk"]


def test_sync_script_compiles_sdk_source_and_updates_n8n_workflow():
    source = SYNC_SCRIPT.read_text(encoding="utf-8")

    assert "parseWorkflowCodeToBuilder" in source
    assert "stripSdkImportBlock" in source
    assert "n8n_combined_messenger_widget_ai_bridge.ts" in source
    assert "builder.validate()" in source
    assert "builder.toJSON()" in source
    assert "N8N_API_URL" in source
    assert "N8N_API_KEY" in source
    assert "N8N_WORKFLOW_ID" in source
    assert "x-n8n-api-key" in source
    assert "method: 'PUT'" in source
    assert 'api/v1/workflows/${workflowId}' in source
    assert 'api/v1/workflows/${workflowId}/activate' in source
    assert "Previous dates and past times are not available" in source
    assert "Do not ask for a time, offer alternatives, or call availability for previous dates" in source


def test_sync_script_loads_vps_env_without_printing_secrets():
    source = SYNC_SCRIPT.read_text(encoding="utf-8")

    assert "loadEnvFile" in source
    assert "N8N_API_KEY" in source
    assert "console.log(apiKey" not in source
    assert "console.error(apiKey" not in source


def test_vps_post_deploy_hook_runs_n8n_sync_before_restart():
    source = POST_DEPLOY_HOOK.read_text(encoding="utf-8")

    assert "source venv/bin/activate" in source
    assert "python manage.py migrate" in source
    assert "python manage.py collectstatic --noinput" in source
    assert "npm install --omit=dev --no-audit --no-fund" in source
    assert "npm run sync:n8n" in source
    assert source.index("npm run sync:n8n") < source.index("systemctl restart")


def test_vps_post_merge_hook_installer_wires_tracked_deploy_hook():
    source = INSTALL_HOOK.read_text(encoding="utf-8")

    assert ".git/hooks/post-merge" in source
    assert "scripts/vps-post-deploy.sh" in source
    assert "chmod +x" in source


def test_env_example_documents_tracked_n8n_sync_hook():
    source = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "scripts/vps-post-deploy.sh" in source
    assert "deploy-vps.ps1" not in source[source.index("n8n API access"):]
