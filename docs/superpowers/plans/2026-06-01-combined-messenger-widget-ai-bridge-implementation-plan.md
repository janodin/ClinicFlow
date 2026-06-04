# Combined Messenger Widget AI Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the active n8n `KliniAssist Messenger + Widget AI Bridge` workflow so Messenger and Widget share one AI Agent, one model node, one memory node, and one set of channel-aware tools.

**Architecture:** Keep the existing Messenger and Widget webhook entry points and final response nodes. Normalize each channel into a canonical shared item, run both through one shared AI core, then route the AI result back to either Facebook Graph API or the Widget webhook response.

**Tech Stack:** n8n Workflow SDK, n8n MCP workflow validation/update tools, Django tool endpoints, HTTP Header Auth credential, OpenAI Chat Model node, n8n Simple Memory, n8n AI Agent.

---

## File Structure

- Create: `n8n_combined_messenger_widget_ai_bridge.ts` - local SDK source for the active n8n workflow so future workflow changes are maintainable and diffable.
- Modify remote n8n workflow: `ZTBqwEzdll6TZsUU` - active `KliniAssist Messenger + Widget AI Bridge` workflow updated from validated SDK code.
- No Django model or view changes are required for the merge. Existing Django endpoints remain the source of truth for tenant scoping and booking validation.
- Do not commit unless the user explicitly asks. Developer instructions prohibit commits without explicit request.

Known live identifiers and credentials:

- Workflow ID: `ZTBqwEzdll6TZsUU`
- Workflow name: `KliniAssist Messenger + Widget AI Bridge`
- Django base URL currently used by the workflow: `https://clinic.example.com`
- n8n inbound webhook base URL currently reported by n8n: `https://n8n.example.com`
- HTTP header auth credential: `KliniAssist N8N Webhook Secret` (`httpHeaderAuth`)
- Model credential: `OpenAI account` (`openAiApi`)
- Shared model to preserve from current Messenger path: `openai/gpt-oss-120b`

---

### Task 1: Create Shared Workflow SDK Source

**Files:**
- Create: `n8n_combined_messenger_widget_ai_bridge.ts`

- [ ] **Step 1: Create the SDK workflow file**

Create `n8n_combined_messenger_widget_ai_bridge.ts` with this full code:

```typescript
import {
  workflow,
  node,
  trigger,
  ifElse,
  switchCase,
  languageModel,
  memory,
  tool,
  newCredential,
  fromAi,
  expr,
} from '@n8n/workflow-sdk';

const DJANGO_BASE_URL = 'https://clinic.example.com';

const GENERIC_WIDGET_FALLBACK = 'Sorry, the assistant is unavailable right now. You can still book an appointment using the booking form.';
const GENERIC_MESSENGER_FALLBACK = 'Thanks for your message. Please contact the clinic directly for help.';

const metaWebhookVerification = trigger({
  type: 'n8n-nodes-base.webhook',
  version: 2.1,
  config: {
    name: 'Meta Webhook Verification',
    position: [240, 160],
    parameters: {
      httpMethod: 'GET',
      path: 'clinicflow-messenger',
      responseMode: 'responseNode',
      options: {},
    },
  },
  output: [
    {
      query: {
        'hub.mode': 'subscribe',
        'hub.challenge': '123456789',
      },
    },
  ],
});

const verifyMetaChallenge = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Verify Meta Challenge',
    position: [464, 160],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const item = $input.first().json;
const query = item.query || {};
const mode = query['hub.mode'] || query.hub?.mode || '';
const challenge = query['hub.challenge'] || query.hub?.challenge || '';
if (mode === 'subscribe' && challenge) {
  return [{ json: { statusCode: 200, body: String(challenge) } }];
}
return [{ json: { statusCode: 403, body: 'Invalid verification request' } }];`,
    },
  },
  output: [{ statusCode: 200, body: '123456789' }],
});

const returnVerificationResponse = node({
  type: 'n8n-nodes-base.respondToWebhook',
  version: 1.5,
  config: {
    name: 'Return Verification Response',
    position: [688, 160],
    parameters: {
      respondWith: 'text',
      responseBody: expr('{{ $json.body }}'),
      options: {
        responseCode: expr('{{ $json.statusCode }}'),
        responseHeaders: {
          entries: [{ name: 'Content-Type', value: 'text/plain' }],
        },
      },
    },
  },
  output: [{ body: '123456789' }],
});

const metaMessengerEvents = trigger({
  type: 'n8n-nodes-base.webhook',
  version: 2.1,
  config: {
    name: 'Meta Messenger Events',
    position: [240, 560],
    parameters: {
      httpMethod: 'POST',
      path: 'clinicflow-messenger',
      options: {
        responseCode: { values: { responseCode: 200 } },
        responseData: 'EVENT_RECEIVED',
      },
    },
  },
  output: [
    {
      body: {
        entry: [
          {
            id: 'PAGE123',
            messaging: [
              {
                sender: { id: 'PSID123' },
                recipient: { id: 'PAGE123' },
                message: { text: 'Can I book a cleaning tomorrow?' },
              },
            ],
          },
        ],
      },
    },
  ],
});

const normalizeMessengerRequest = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Normalize Messenger Request',
    position: [464, 560],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const input = $input.first().json;
const body = input.body || input;
const entry = body.entry?.[0] || {};
const messaging = entry.messaging?.[0] || {};
const pageId = String(entry.id || messaging.recipient?.id || '').trim();
const psid = String(messaging.sender?.id || '').trim();
const text = String(messaging.message?.text || '').trim();
if (!pageId || !psid || !text) {
  return [];
}
return [{
  json: {
    channel: 'messenger',
    message: text,
    page_id: pageId,
    psid,
    clinic_slug: '',
    session_id: '',
    session_key: 'messenger:' + pageId + ':' + psid,
  },
}];`,
    },
  },
  output: [
    {
      channel: 'messenger',
      message: 'Can I book a cleaning tomorrow?',
      page_id: 'PAGE123',
      psid: 'PSID123',
      clinic_slug: '',
      session_id: '',
      session_key: 'messenger:PAGE123:PSID123',
    },
  ],
});

const getMessengerClinicContext = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Get Messenger Clinic Context',
    position: [688, 560],
    parameters: {
      method: 'POST',
      url: `${DJANGO_BASE_URL}/messenger/ai/context/`,
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: {
        parameters: [{ name: 'Content-Type', value: 'application/json' }],
      },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { page_id: $json.page_id } }}'),
      options: {
        response: { response: { neverError: true, responseFormat: 'json' } },
        timeout: 15000,
      },
    },
    credentials: {
      httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret'),
    },
  },
  output: [
    {
      found: true,
      page_id: 'PAGE123',
      page_token: 'PAGE_TOKEN',
      clinic: { name: 'Demo Clinic', timezone: 'Asia/Manila' },
      current_time: { timezone: 'Asia/Manila', now: '2026-06-01T09:00:00+08:00', today: '2026-06-01' },
      ai: { is_ai_enabled: true, instructions: 'Be helpful.', fallback_message: GENERIC_MESSENGER_FALLBACK },
      services: [],
      faqs: [],
    },
  ],
});

const buildMessengerSharedInput = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Build Messenger Shared Input',
    position: [912, 560],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const context = $input.first().json || {};
const source = $('Normalize Messenger Request').first().json || {};
const fallback = context.ai?.fallback_message || '${GENERIC_MESSENGER_FALLBACK}';
return [{
  json: {
    ...source,
    context,
    fallback_message: fallback,
    output_mode: 'facebook',
  },
}];`,
    },
  },
  output: [
    {
      channel: 'messenger',
      message: 'Can I book a cleaning tomorrow?',
      page_id: 'PAGE123',
      psid: 'PSID123',
      clinic_slug: '',
      session_id: '',
      session_key: 'messenger:PAGE123:PSID123',
      fallback_message: GENERIC_MESSENGER_FALLBACK,
      output_mode: 'facebook',
      context: { found: true, ai: { is_ai_enabled: true } },
    },
  ],
});

const widgetAssistantWebhook = trigger({
  type: 'n8n-nodes-base.webhook',
  version: 2.1,
  config: {
    name: 'Widget Assistant Webhook',
    position: [240, 1040],
    parameters: {
      httpMethod: 'POST',
      path: 'clinicflow-widget-assistant',
      responseMode: 'responseNode',
      options: {},
    },
  },
  output: [
    {
      body: {
        channel: 'widget',
        clinic_id: 1,
        clinic_slug: 'demo-clinic',
        message: 'Can I book tomorrow?',
        history: [],
        session_id: 'SESSION123',
      },
    },
  ],
});

const normalizeWidgetRequest = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Normalize Widget Request',
    position: [464, 1040],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const input = $input.first().json;
const body = input.body || input;
const clinicSlug = String(body.clinic_slug || body.clinicSlug || '').trim();
const clinicId = body.clinic_id || body.clinicId || '';
const message = String(body.message || body.text || '').trim();
const history = Array.isArray(body.history) ? body.history.slice(-10) : [];
const sessionId = String(body.session_id || body.sessionId || '').trim();
const usableSessionId = sessionId || ('stateless:' + $execution.id);
return [{
  json: {
    channel: 'widget',
    message,
    clinic_slug: clinicSlug,
    clinic_id: clinicId,
    page_id: '',
    psid: '',
    history,
    session_id: usableSessionId,
    session_key: 'widget:' + (clinicSlug || 'unknown-clinic') + ':' + usableSessionId,
  },
}];`,
    },
  },
  output: [
    {
      channel: 'widget',
      message: 'Can I book tomorrow?',
      clinic_slug: 'demo-clinic',
      clinic_id: 1,
      page_id: '',
      psid: '',
      history: [],
      session_id: 'SESSION123',
      session_key: 'widget:demo-clinic:SESSION123',
    },
  ],
});

const getWidgetClinicContext = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Get Widget Clinic Context',
    position: [688, 1040],
    parameters: {
      method: 'POST',
      url: `${DJANGO_BASE_URL}/messenger/ai/widget/context/`,
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: {
        parameters: [{ name: 'Content-Type', value: 'application/json' }],
      },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { clinic_slug: $json.clinic_slug } }}'),
      options: {
        response: { response: { neverError: true, responseFormat: 'json' } },
        timeout: 15000,
      },
    },
    credentials: {
      httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret'),
    },
  },
  output: [
    {
      found: true,
      channel: 'widget',
      clinic: { id: 1, slug: 'demo-clinic', name: 'Demo Clinic', timezone: 'Asia/Manila' },
      current_time: { timezone: 'Asia/Manila', now: '2026-06-01T09:00:00+08:00', today: '2026-06-01' },
      ai: { is_ai_enabled: true, instructions: 'Be helpful.', fallback_message: GENERIC_WIDGET_FALLBACK },
      services: [],
      faqs: [],
    },
  ],
});

const buildWidgetSharedInput = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Build Widget Shared Input',
    position: [912, 1040],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const context = $input.first().json || {};
const source = $('Normalize Widget Request').first().json || {};
const fallback = context.ai?.fallback_message || '${GENERIC_WIDGET_FALLBACK}';
return [{
  json: {
    ...source,
    context,
    fallback_message: fallback,
    output_mode: 'widget_json',
  },
}];`,
    },
  },
  output: [
    {
      channel: 'widget',
      message: 'Can I book tomorrow?',
      clinic_slug: 'demo-clinic',
      page_id: '',
      psid: '',
      session_id: 'SESSION123',
      session_key: 'widget:demo-clinic:SESSION123',
      fallback_message: GENERIC_WIDGET_FALLBACK,
      output_mode: 'widget_json',
      context: { found: true, ai: { is_ai_enabled: true } },
    },
  ],
});

const sharedAiInput = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Shared AI Input',
    position: [1136, 800],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `return $input.all();`,
    },
  },
  output: [
    {
      channel: 'widget',
      message: 'Can I book tomorrow?',
      clinic_slug: 'demo-clinic',
      page_id: '',
      psid: '',
      session_key: 'widget:demo-clinic:SESSION123',
      fallback_message: GENERIC_WIDGET_FALLBACK,
      context: { found: true, ai: { is_ai_enabled: true } },
    },
  ],
});

const checkSharedAiEnabled = ifElse({
  version: 2.3,
  config: {
    name: 'Check Shared AI Enabled',
    position: [1360, 800],
    parameters: {
      conditions: {
        options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
        conditions: [
          {
            leftValue: expr('{{ $json.context?.found }}'),
            rightValue: true,
            operator: { type: 'boolean', operation: 'equals' },
          },
          {
            leftValue: expr('{{ $json.context?.ai?.is_ai_enabled }}'),
            rightValue: true,
            operator: { type: 'boolean', operation: 'equals' },
          },
          {
            leftValue: expr('{{ !!$json.message }}'),
            rightValue: true,
            operator: { type: 'boolean', operation: 'equals' },
          },
        ],
        combinator: 'and',
      },
    },
  },
});

const sharedChatModel = languageModel({
  type: '@n8n/n8n-nodes-langchain.lmChatOpenAi',
  version: 1.3,
  config: {
    name: 'Shared Chat Model',
    position: [1536, 1040],
    parameters: {
      model: { __rl: true, value: 'openai/gpt-oss-120b', mode: 'list', cachedResultName: 'openai/gpt-oss-120b' },
      responsesApiEnabled: false,
      options: { temperature: 0.2 },
    },
    credentials: {
      openAiApi: newCredential('OpenAI account'),
    },
  },
  output: [{ response: 'Assistant reply' }],
});

const sharedConversationMemory = memory({
  type: '@n8n/n8n-nodes-langchain.memoryBufferWindow',
  version: 1.4,
  config: {
    name: 'Shared Conversation Memory',
    position: [1664, 1040],
    parameters: {
      sessionIdType: 'customKey',
      sessionKey: expr('{{ $("Shared AI Input").item.json.session_key + ":shared:v1" }}'),
      contextWindowLength: 8,
    },
  },
  output: [{ messages: [] }],
});

const matchServicesTool = tool({
  type: 'n8n-nodes-base.httpRequestTool',
  version: 4.4,
  config: {
    name: 'match_services',
    position: [1792, 1040],
    parameters: {
      method: 'POST',
      url: expr('{{ $("Shared AI Input").item.json.channel === "messenger" ? "' + DJANGO_BASE_URL + '/messenger/ai/services/" : "' + DJANGO_BASE_URL + '/messenger/ai/widget/services/" }}'),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: {
        parameters: [{ name: 'Content-Type', value: 'application/json' }],
      },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: {
        page_id: expr('{{ $("Shared AI Input").item.json.channel === "messenger" ? $("Shared AI Input").item.json.page_id : "" }}'),
        clinic_slug: expr('{{ $("Shared AI Input").item.json.channel === "widget" ? $("Shared AI Input").item.json.clinic_slug : "" }}'),
        query: fromAi('query', 'Service name or user phrase to match against clinic services'),
      },
      options: {},
      optimizeResponse: true,
    },
    credentials: {
      httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret'),
    },
  },
  output: [{ found: true, matches: [] }],
});

const checkAvailabilityTool = tool({
  type: 'n8n-nodes-base.httpRequestTool',
  version: 4.4,
  config: {
    name: 'check_availability',
    position: [1920, 1040],
    parameters: {
      method: 'POST',
      url: expr('{{ $("Shared AI Input").item.json.channel === "messenger" ? "' + DJANGO_BASE_URL + '/messenger/ai/availability/" : "' + DJANGO_BASE_URL + '/messenger/ai/widget/availability/" }}'),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: {
        parameters: [{ name: 'Content-Type', value: 'application/json' }],
      },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: {
        page_id: expr('{{ $("Shared AI Input").item.json.channel === "messenger" ? $("Shared AI Input").item.json.page_id : "" }}'),
        clinic_slug: expr('{{ $("Shared AI Input").item.json.channel === "widget" ? $("Shared AI Input").item.json.clinic_slug : "" }}'),
        service_id: fromAi('service_id', 'Numeric service ID selected from clinic services'),
        preferred_starts_at: fromAi('preferred_starts_at', 'Clinic-local ISO datetime with timezone offset when the user gives an exact time, otherwise blank'),
        preferred_date: fromAi('preferred_date', 'Clinic-local requested appointment date as YYYY-MM-DD when the user asks about a date, otherwise blank'),
      },
      options: {},
      optimizeResponse: true,
    },
    credentials: {
      httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret'),
    },
  },
  output: [{ found: true, available: true, alternatives: [] }],
});

const bookConfirmedAppointmentTool = tool({
  type: 'n8n-nodes-base.httpRequestTool',
  version: 4.4,
  config: {
    name: 'book_confirmed_appointment',
    position: [2048, 1040],
    parameters: {
      method: 'POST',
      url: expr('{{ $("Shared AI Input").item.json.channel === "messenger" ? "' + DJANGO_BASE_URL + '/messenger/ai/book/" : "' + DJANGO_BASE_URL + '/messenger/ai/widget/book/" }}'),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: {
        parameters: [{ name: 'Content-Type', value: 'application/json' }],
      },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: {
        page_id: expr('{{ $("Shared AI Input").item.json.channel === "messenger" ? $("Shared AI Input").item.json.page_id : "" }}'),
        clinic_slug: expr('{{ $("Shared AI Input").item.json.channel === "widget" ? $("Shared AI Input").item.json.clinic_slug : "" }}'),
        service_id: fromAi('service_id', 'Numeric service ID selected from clinic services'),
        starts_at: fromAi('starts_at', 'Confirmed appointment start time as clinic-local ISO 8601 datetime with timezone offset'),
        full_name: fromAi('full_name', 'Patient full name'),
        phone: fromAi('phone', 'Patient phone number'),
        email: fromAi('email', 'Patient email if provided, otherwise blank'),
        reason: fromAi('reason', 'Patient reason or notes if provided, otherwise blank'),
        confirmed: fromAi('confirmed', 'Boolean true only after the user explicitly confirms the summarized appointment'),
      },
      options: {},
      optimizeResponse: true,
    },
    credentials: {
      httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret'),
    },
  },
  output: [{ created: false, error: 'Appointment creation requires explicit user confirmation.' }],
});

const clinicFlowSharedAiAgent = node({
  type: '@n8n/n8n-nodes-langchain.agent',
  version: 3.1,
  config: {
    name: 'KliniAssist Shared AI Agent',
    position: [1744, 720],
    parameters: {
      promptType: 'define',
      text: expr('{{ $("Shared AI Input").item.json.message }}'),
      options: {
        systemMessage: expr('KliniAssist Shared Messenger + Widget AI Instructions:\n' +
          '{{ $("Shared AI Input").item.json.context?.ai?.instructions || "No custom clinic instructions configured." }}\n\n' +
          'Channel: {{ $("Shared AI Input").item.json.channel }}\n' +
          'Output mode: {{ $("Shared AI Input").item.json.output_mode }}\n\n' +
          'Clinic context JSON:\n' +
          '{{ JSON.stringify($("Shared AI Input").item.json.context || {}) }}\n\n' +
          'Current clinic date/time from Django context:\n' +
          '- Timezone: {{ $("Shared AI Input").item.json.context?.current_time?.timezone || $("Shared AI Input").item.json.context?.clinic?.timezone || "UTC" }}\n' +
          '- Now: {{ $("Shared AI Input").item.json.context?.current_time?.now || $now.setZone($("Shared AI Input").item.json.context?.clinic?.timezone || "UTC").toISO() }}\n' +
          '- Today: {{ $("Shared AI Input").item.json.context?.current_time?.today || $now.setZone($("Shared AI Input").item.json.context?.clinic?.timezone || "UTC").toISODate() }}\n\n' +
          'Rules:\n' +
          '- Use clinic context and Django tools as the source of truth.\n' +
          '- Use match_services for service matching.\n' +
          '- Use check_availability before claiming appointment availability.\n' +
          '- Collect service, date/time, full name, and phone before booking.\n' +
          '- Summarize the appointment and ask for explicit confirmation before booking.\n' +
          '- Only call book_confirmed_appointment after explicit user confirmation.\n' +
          '- For Messenger, reply as concise plain Facebook Messenger text.\n' +
          '- For Widget, reply concisely and keep the existing booking form usable.\n' +
          '- Do not expose secrets, invent clinic data, give medical diagnosis, or create appointments without tool validation.'),
        maxIterations: 8,
        returnIntermediateSteps: false,
      },
    },
    subnodes: {
      model: sharedChatModel,
      memory: sharedConversationMemory,
      tools: [matchServicesTool, checkAvailabilityTool, bookConfirmedAppointmentTool],
    },
  },
  output: [{ output: 'Assistant reply' }],
});

const prepareSharedFallback = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Prepare Shared Fallback',
    position: [1600, 912],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const item = $input.first().json || {};
const fallback = item.fallback_message || (item.channel === 'messenger' ? '${GENERIC_MESSENGER_FALLBACK}' : '${GENERIC_WIDGET_FALLBACK}');
return [{ json: { output: fallback } }];`,
    },
  },
  output: [{ output: GENERIC_WIDGET_FALLBACK }],
});

const prepareChannelReply = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Prepare Channel Reply',
    position: [2192, 800],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const input = $input.first().json || {};
const shared = $('Shared AI Input').first().json || {};
const context = shared.context || {};
const channel = shared.channel || 'widget';
const genericFallback = channel === 'messenger' ? '${GENERIC_MESSENGER_FALLBACK}' : '${GENERIC_WIDGET_FALLBACK}';
let text = input.output || input.text || input.response || input.reply || shared.fallback_message || genericFallback;
text = String(text).replace(/<think[\s\S]*?<\/think>/gi, '').replace(/<\/?think>/gi, '').trim();
if (!text) {
  text = shared.fallback_message || genericFallback;
}
const maxLength = channel === 'messenger' ? 1900 : 1800;
if (text.length > maxLength) {
  text = text.slice(0, maxLength);
}
return [{
  json: {
    ...shared,
    reply_text: text,
    access_token: context.page_token || '',
    facebook_body: {
      recipient: { id: shared.psid || '' },
      message: { text },
    },
    widget_body: { reply: text },
  },
}];`,
    },
  },
  output: [
    {
      channel: 'widget',
      reply_text: 'Assistant reply',
      access_token: '',
      facebook_body: { recipient: { id: '' }, message: { text: 'Assistant reply' } },
      widget_body: { reply: 'Assistant reply' },
    },
  ],
});

const routeChannelReply = switchCase({
  version: 3.4,
  config: {
    name: 'Route Channel Reply',
    position: [2416, 800],
    parameters: {
      mode: 'rules',
      rules: {
        values: [
          {
            renameOutput: true,
            outputKey: 'messenger',
            conditions: {
              options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
              conditions: [
                {
                  leftValue: expr('{{ $json.channel }}'),
                  rightValue: 'messenger',
                  operator: { type: 'string', operation: 'equals' },
                },
              ],
              combinator: 'and',
            },
          },
          {
            renameOutput: true,
            outputKey: 'widget',
            conditions: {
              options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
              conditions: [
                {
                  leftValue: expr('{{ $json.channel }}'),
                  rightValue: 'widget',
                  operator: { type: 'string', operation: 'equals' },
                },
              ],
              combinator: 'and',
            },
          },
        ],
      },
      options: { fallbackOutput: 'none' },
    },
  },
});

const sendFacebookReply = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Send Facebook Reply',
    position: [2640, 640],
    parameters: {
      method: 'POST',
      url: 'https://graph.facebook.com/v18.0/me/messages',
      sendQuery: true,
      queryParameters: {
        parameters: [{ name: 'access_token', value: expr('{{ $json.access_token }}') }],
      },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ $json.facebook_body }}'),
      options: {
        response: { response: { neverError: true, responseFormat: 'json' } },
        timeout: 15000,
      },
    },
  },
  output: [{ recipient_id: 'PSID123', message_id: 'mid.123' }],
});

const returnWidgetReply = node({
  type: 'n8n-nodes-base.respondToWebhook',
  version: 1.5,
  config: {
    name: 'Return Widget Reply',
    position: [2640, 960],
    parameters: {
      respondWith: 'json',
      responseBody: expr('{{ $json.widget_body }}'),
      options: {
        responseCode: 200,
        responseHeaders: {
          entries: [{ name: 'Content-Type', value: 'application/json' }],
        },
      },
    },
  },
  output: [{ reply: 'Assistant reply' }],
});

export default workflow('ZTBqwEzdll6TZsUU', 'KliniAssist Messenger + Widget AI Bridge')
  .add(metaWebhookVerification)
  .to(verifyMetaChallenge)
  .to(returnVerificationResponse)
  .add(metaMessengerEvents)
  .to(normalizeMessengerRequest)
  .to(getMessengerClinicContext)
  .to(buildMessengerSharedInput)
  .to(sharedAiInput)
  .to(checkSharedAiEnabled
    .onTrue(clinicFlowSharedAiAgent.to(prepareChannelReply).to(routeChannelReply
      .onCase('messenger', sendFacebookReply)
      .onCase('widget', returnWidgetReply)))
    .onFalse(prepareSharedFallback.to(prepareChannelReply).to(routeChannelReply
      .onCase('messenger', sendFacebookReply)
      .onCase('widget', returnWidgetReply))))
  .add(widgetAssistantWebhook)
  .to(normalizeWidgetRequest)
  .to(getWidgetClinicContext)
  .to(buildWidgetSharedInput)
  .to(sharedAiInput);
```

- [ ] **Step 2: Check the file is present**

Run: `Test-Path -LiteralPath "n8n_combined_messenger_widget_ai_bridge.ts"`

Expected: `True`

---

### Task 2: Validate The Workflow SDK Code

**Files:**
- Read: `n8n_combined_messenger_widget_ai_bridge.ts`

- [ ] **Step 1: Load the SDK source**

Read the full contents of `n8n_combined_messenger_widget_ai_bridge.ts`.

- [ ] **Step 2: Validate with n8n MCP**

Call `validate_workflow` with the exact file contents.

Expected: validation succeeds with no SDK parse errors and no missing required node parameters.

- [ ] **Step 3: Fix validation errors if any**

If validation fails, update only `n8n_combined_messenger_widget_ai_bridge.ts` and re-run `validate_workflow`.

Common expected fixes:

```typescript
// IF and Switch conditions must keep options, conditions, and combinator together.
conditions: {
  options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
  conditions: [
    {
      leftValue: expr('{{ $json.channel }}'),
      rightValue: 'widget',
      operator: { type: 'string', operation: 'equals' },
    },
  ],
  combinator: 'and',
}
```

Expected: validation succeeds before updating the active workflow.

---

### Task 3: Update The Active n8n Workflow

**Remote workflow:**
- Update: `ZTBqwEzdll6TZsUU`

- [ ] **Step 1: Update workflow from validated SDK code**

Call `update_workflow` with:

```json
{
  "workflowId": "ZTBqwEzdll6TZsUU",
  "name": "KliniAssist Messenger + Widget AI Bridge",
  "description": "Combined KliniAssist Meta Messenger and website widget AI bridge with one shared AI Agent, model, memory, and channel-aware booking tools.",
  "code": "<validated contents of n8n_combined_messenger_widget_ai_bridge.ts>"
}
```

Expected: n8n saves a new draft version of the workflow.

- [ ] **Step 2: Inspect updated workflow details**

Call `get_workflow_details` for `ZTBqwEzdll6TZsUU`.

Expected structure:

- Three triggers remain: `Meta Webhook Verification`, `Meta Messenger Events`, `Widget Assistant Webhook`.
- One AI Agent exists: `KliniAssist Shared AI Agent`.
- One model exists: `Shared Chat Model`.
- One memory node exists: `Shared Conversation Memory`.
- Three tools exist: `match_services`, `check_availability`, `book_confirmed_appointment`.
- Separate final outputs remain: `Send Facebook Reply`, `Return Widget Reply`.

---

### Task 4: Test The Draft Workflow With Pin Data

**Remote workflow:**
- Test: `ZTBqwEzdll6TZsUU`

- [ ] **Step 1: Prepare test pin data**

Call `prepare_test_pin_data` for `ZTBqwEzdll6TZsUU`.

Expected: schemas are returned for trigger nodes, credential nodes, HTTP Request nodes, and AI/model nodes that need pinning.

- [ ] **Step 2: Test the Widget trigger path**

Call `test_workflow` with trigger node `Widget Assistant Webhook` and pin data shaped like this where required:

```json
{
  "Widget Assistant Webhook": [
    {
      "json": {
        "body": {
          "channel": "widget",
          "clinic_id": 1,
          "clinic_slug": "demo-clinic",
          "message": "Can I book tomorrow?",
          "history": [],
          "session_id": "SESSION123"
        }
      }
    }
  ],
  "Get Widget Clinic Context": [
    {
      "json": {
        "found": true,
        "channel": "widget",
        "clinic": { "id": 1, "slug": "demo-clinic", "name": "Demo Clinic", "timezone": "Asia/Manila" },
        "current_time": { "timezone": "Asia/Manila", "now": "2026-06-01T09:00:00+08:00", "today": "2026-06-01" },
        "ai": { "is_ai_enabled": true, "instructions": "Answer booking questions and use tools for booking.", "fallback_message": "Clinic fallback." },
        "services": [{ "id": 1, "name": "Cleaning", "duration_minutes": 30, "display_price": "1000" }],
        "faqs": []
      }
    }
  ],
  "KliniAssist Shared AI Agent": [
    { "json": { "output": "Sure, what time works for you tomorrow?" } }
  ]
}
```

Expected: `Return Widget Reply` receives `{ "reply": "Sure, what time works for you tomorrow?" }`.

- [ ] **Step 3: Test the Messenger trigger path**

Call `test_workflow` with trigger node `Meta Messenger Events` and pin data shaped like this where required:

```json
{
  "Meta Messenger Events": [
    {
      "json": {
        "body": {
          "entry": [
            {
              "id": "PAGE123",
              "messaging": [
                {
                  "sender": { "id": "PSID123" },
                  "recipient": { "id": "PAGE123" },
                  "message": { "text": "Can I book cleaning tomorrow?" }
                }
              ]
            }
          ]
        }
      }
    }
  ],
  "Get Messenger Clinic Context": [
    {
      "json": {
        "found": true,
        "page_id": "PAGE123",
        "page_token": "PAGE_TOKEN",
        "clinic": { "id": 1, "name": "Demo Clinic", "timezone": "Asia/Manila" },
        "current_time": { "timezone": "Asia/Manila", "now": "2026-06-01T09:00:00+08:00", "today": "2026-06-01" },
        "ai": { "is_ai_enabled": true, "instructions": "Answer booking questions and use tools for booking.", "fallback_message": "Clinic fallback." },
        "services": [{ "id": 1, "name": "Cleaning", "duration_minutes": 30, "display_price": "1000" }],
        "faqs": []
      }
    }
  ],
  "KliniAssist Shared AI Agent": [
    { "json": { "output": "Sure, what time works for you tomorrow?" } }
  ],
  "Send Facebook Reply": [
    { "json": { "recipient_id": "PSID123", "message_id": "mid.123" } }
  ]
}
```

Expected: `Send Facebook Reply` receives a body with `recipient.id = "PSID123"` and message text `Sure, what time works for you tomorrow?`.

- [ ] **Step 4: Test disabled AI fallback path**

Run one widget test with `Get Widget Clinic Context.ai.is_ai_enabled = false`.

Expected: `Return Widget Reply` receives the configured fallback message and `KliniAssist Shared AI Agent` does not execute.

---

### Task 5: Publish And Verify Production Workflow

**Remote workflow:**
- Publish: `ZTBqwEzdll6TZsUU`

- [ ] **Step 1: Publish the draft workflow**

Call `publish_workflow` for `ZTBqwEzdll6TZsUU`.

Expected: the active version updates successfully.

- [ ] **Step 2: Re-fetch production trigger details**

Call `get_workflow_details` for `ZTBqwEzdll6TZsUU`.

Expected trigger details remain:

- GET `/webhook/clinicflow-messenger` for Meta verification.
- POST `/webhook/clinicflow-messenger` for Messenger events.
- POST `/webhook/clinicflow-widget-assistant` for Widget assistant.

- [ ] **Step 3: Run Django regression checks**

Run from the repository root:

```powershell
.\env\Scripts\python.exe -m pytest messenger/tests.py widget/tests.py -q
```

Expected: all Messenger and Widget tests pass. These tests verify Django-side secret validation, tenant scoping, AI fallback behavior, and booking validation remain intact.

- [ ] **Step 4: Run Django system check**

Run from the repository root:

```powershell
.\env\Scripts\python.exe manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 5: Review local diff**

Run:

```powershell
git diff -- docs/superpowers/specs/2026-06-01-combined-messenger-widget-ai-bridge-design.md docs/superpowers/plans/2026-06-01-combined-messenger-widget-ai-bridge-implementation-plan.md n8n_combined_messenger_widget_ai_bridge.ts
```

Expected: only the approved spec, this plan, and the local n8n SDK workflow source are changed.

Do not commit unless the user explicitly asks.

---

## Self-Review

Spec coverage:

- Shared model/agent/memory/tools are covered by Task 1 and verified in Task 3.
- Separate Messenger and Widget inputs/outputs are preserved in Task 1 and verified in Task 4.
- Existing Django endpoint contracts remain unchanged and are used by the shared tools.
- Tenant identifiers are injected from `Shared AI Input`, not AI-generated values.
- Memory keys are channel-prefixed and include page/PSID or clinic/session.
- Publishing and regression checks are covered in Task 5.

Completion-marker scan:

- The plan contains no incomplete markers.
- The only `<validated contents...>` marker is the concrete handoff value for the MCP update call and refers to the file created in Task 1.

Type consistency:

- Node names referenced by expressions match node declarations: `Shared AI Input`, `Normalize Messenger Request`, and `Normalize Widget Request`.
- Tool names in the system prompt match connected tools: `match_services`, `check_availability`, and `book_confirmed_appointment`.
- Credential names match accessible n8n credentials: `KliniAssist N8N Webhook Secret` and `OpenAI account`.
