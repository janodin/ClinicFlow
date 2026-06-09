#!/usr/bin/env node

import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseWorkflowCodeToBuilder } from '@n8n/workflow-sdk';

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptDir, '..');
const defaultWorkflowPath = resolve(repoRoot, 'n8n_combined_messenger_widget_ai_bridge.ts');
const defaultEnvPath = resolve(repoRoot, '.env');
const REQUIRED_LIVE_PHRASES = [
  'Previous dates and past times are not available',
  'Do not ask for a time, offer alternatives, or call availability for previous dates',
];

function parseArgs(argv) {
  const options = {
    dryRun: false,
    envPath: defaultEnvPath,
    workflowPath: defaultWorkflowPath,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--dry-run') {
      options.dryRun = true;
      continue;
    }
    if (arg === '--env-file') {
      options.envPath = resolve(repoRoot, argv[index + 1] || '');
      index += 1;
      continue;
    }
    if (arg === '--workflow-file') {
      options.workflowPath = resolve(repoRoot, argv[index + 1] || '');
      index += 1;
      continue;
    }
    throw new Error(`Unknown argument: ${arg}`);
  }
  return options;
}

function stripOuterQuotes(value) {
  const trimmed = value.trim();
  if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function loadEnvFile(filePath) {
  if (!existsSync(filePath)) {
    return;
  }
  const lines = readFileSync(filePath, 'utf-8').split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) {
      continue;
    }
    const separator = trimmed.indexOf('=');
    if (separator === -1) {
      continue;
    }
    const key = trimmed.slice(0, separator).trim();
    const value = stripOuterQuotes(trimmed.slice(separator + 1));
    if (key && process.env[key] === undefined) {
      process.env[key] = value;
    }
  }
}

function stripSdkImportBlock(code) {
  return code.replace(/^\s*import\s*\{[\s\S]*?\}\s*from\s*['"]@n8n\/workflow-sdk['"];\s*/, '');
}

function requireEnv(name) {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required for n8n workflow sync.`);
  }
  return value;
}

function requireHeaderEnv(name) {
  const value = requireEnv(name);
  if (/[\u0000-\u001F\u007F]/.test(value)) {
    throw new Error(`${name} contains newline or control characters; re-enter it as a single line.`);
  }
  return value;
}

function normalizeApiBase(value) {
  return value.trim().replace(/\/$/, '').replace(/\/api\/v1$/, '');
}

function buildWorkflowPayload(workflowJson) {
  return {
    name: workflowJson.name,
    nodes: workflowJson.nodes,
    connections: workflowJson.connections,
    settings: workflowJson.settings || {},
    pinData: workflowJson.pinData || {},
  };
}

function assertRequiredPhrases(value, context) {
  for (const phrase of REQUIRED_LIVE_PHRASES) {
    if (!value.includes(phrase)) {
      throw new Error(`${context} is missing required phrase: ${phrase}`);
    }
  }
}

async function n8nRequest(apiBase, apiKey, path, options = {}) {
  const response = await fetch(`${apiBase}/${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'x-n8n-api-key': apiKey,
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${options.method || 'GET'} /${path} failed with HTTP ${response.status}: ${text.slice(0, 500)}`);
  }
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`/${path} returned non-JSON response: ${text.slice(0, 200)}`);
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  loadEnvFile(options.envPath);

  const workflowCode = readFileSync(options.workflowPath, 'utf-8');
  assertRequiredPhrases(workflowCode, 'Workflow source');

  const builder = parseWorkflowCodeToBuilder(stripSdkImportBlock(workflowCode));
  const validation = builder.validate();
  if (validation.errors.length > 0) {
    throw new Error(`Workflow validation failed:\n${validation.errors.map((error) => `- ${error.message}`).join('\n')}`);
  }
  for (const warning of validation.warnings) {
    console.warn(`Workflow validation warning: ${warning.message}`);
  }

  const workflowJson = builder.toJSON();
  assertRequiredPhrases(JSON.stringify(workflowJson), 'Compiled workflow JSON');
  const workflowId = process.env.N8N_WORKFLOW_ID?.trim() || workflowJson.id;
  if (!workflowId) {
    throw new Error('N8N_WORKFLOW_ID is required because the workflow source does not include an ID.');
  }

  if (options.dryRun) {
    console.log(`Dry run passed for n8n workflow ${workflowId}.`);
    return;
  }

  const apiBase = normalizeApiBase(requireEnv('N8N_API_URL'));
  const apiKey = requireHeaderEnv('N8N_API_KEY');
  const payload = buildWorkflowPayload(workflowJson);

  console.log(`Syncing n8n workflow ${workflowId} from ${options.workflowPath}...`);
  await n8nRequest(apiBase, apiKey, `api/v1/workflows/${workflowId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });

  if (process.env.N8N_ACTIVATE_WORKFLOW !== 'false') {
    await n8nRequest(apiBase, apiKey, `api/v1/workflows/${workflowId}/activate`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
  }

  const liveWorkflow = await n8nRequest(apiBase, apiKey, `api/v1/workflows/${workflowId}`);
  assertRequiredPhrases(JSON.stringify(liveWorkflow), 'Live n8n workflow');
  console.log(`n8n workflow ${workflowId} is synced and verified.`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
