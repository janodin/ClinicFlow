import {
  workflow,
  node,
  trigger,
  switchCase,
  languageModel,
  memory,
  tool,
  newCredential,
  fromAi,
  expr,
} from '@n8n/workflow-sdk';

const DJANGO_BASE_URL_EXPR = '($env.DJANGO_BASE_URL || "https://178-105-83-211.nip.io").replace(/\\/$/, "")';
const N8N_WEBHOOK_CREDENTIAL_ID = 'PJHqVMwE3qU58s9E';
const MESSENGER_FALLBACK = 'Thanks for your message. Please contact the clinic directly for help.';
const WIDGET_FALLBACK = 'Sorry, the assistant is unavailable right now. You can still book an appointment using the booking form.';

const metaWebhookVerification = trigger({
  type: 'n8n-nodes-base.webhook',
  version: 2.1,
  config: {
    name: 'Meta Webhook Verification',
    position: [240, 160],
    parameters: {
      httpMethod: 'GET',
      path: 'kliniassist-messenger',
      responseMode: 'responseNode',
      options: {},
    },
  },
  output: [{ query: { 'hub.mode': 'subscribe', 'hub.verify_token': 'configured-token', 'hub.challenge': '123456789' } }],
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
const token = String(query['hub.verify_token'] || query.hub?.verify_token || '').trim();
const challenge = query['hub.challenge'] || query.hub?.challenge || '';
const expectedToken = String('{{ $env.MESSENGER_VERIFY_TOKEN || "" }}').trim();
if (mode === 'subscribe' && expectedToken && token === expectedToken && challenge) {
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
        responseHeaders: { entries: [{ name: 'Content-Type', value: 'text/plain' }] },
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
      path: 'kliniassist-messenger',
      responseMode: 'responseNode',
      options: { rawBody: true },
    },
  },
  output: [{ headers: { 'X-Hub-Signature-256': 'sha256=abc123' }, body: { entry: [{ id: 'PAGE123', messaging: [{ sender: { id: 'PSID123' }, recipient: { id: 'PAGE123' }, message: { text: 'Can I book cleaning tomorrow?' } }] }] } }],
});

const acknowledgeMetaMessengerEvent = node({
  type: 'n8n-nodes-base.respondToWebhook',
  version: 1.5,
  config: {
    name: 'Acknowledge Meta Messenger Event',
    position: [464, 400],
    parameters: {
      respondWith: 'text',
      responseBody: 'EVENT_RECEIVED',
      options: {
        responseCode: 200,
        responseHeaders: { entries: [{ name: 'Content-Type', value: 'text/plain' }] },
      },
    },
  },
  output: [{ headers: { 'X-Hub-Signature-256': 'sha256=abc123' }, body: { entry: [{ id: 'PAGE123', messaging: [{ sender: { id: 'PSID123' }, recipient: { id: 'PAGE123' }, message: { text: 'Can I book cleaning tomorrow?' } }] }] } }],
});

const normalizeMessengerRequest = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Normalize Messenger Request',
    position: [464, 560],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const inputItem = $input.first();
const input = inputItem.json || {};
let rawBody = typeof input.rawBody === 'string' ? input.rawBody : '';
if (!rawBody && typeof inputItem.binary?.data?.data === 'string') {
  rawBody = Buffer.from(inputItem.binary.data.data, 'base64').toString('utf8');
}
let body = input.body || input;
if (typeof body === 'string') {
  try {
    body = JSON.parse(body);
  } catch (error) {
    return [];
  }
}
if (!rawBody && body && typeof body === 'object') {
  rawBody = JSON.stringify(body);
}
const headers = input.headers || {};
const signature = String(headers['X-Hub-Signature-256'] || headers['x-hub-signature-256'] || '').trim();
const entries = Array.isArray(body.entry) ? body.entry : [];
const items = [];
for (const entry of entries) {
  const messagingItems = Array.isArray(entry.messaging) ? entry.messaging : [];
  for (const messaging of messagingItems) {
    const pageId = String(entry.id || messaging.recipient?.id || '').trim();
    const psid = String(messaging.sender?.id || '').trim();
    const message = String(messaging.message?.text || '').trim();
    const postback = String(messaging.postback?.payload || messaging.message?.quick_reply?.payload || '').trim();
    if (!pageId || !psid || (!message && !postback)) {
      continue;
    }
    items.push({ json: {
      channel: 'messenger',
      message,
      postback,
      page_id: pageId,
      psid,
      clinic_slug: '',
      session_id: '',
      session_key: 'messenger:' + pageId + ':' + psid,
      output_mode: 'facebook',
      raw_body: rawBody,
      signature
    } });
  }
}
return items;`,
    },
  },
  output: [{ channel: 'messenger', message: 'Can I book cleaning tomorrow?', postback: '', page_id: 'PAGE123', psid: 'PSID123', clinic_slug: '', session_id: '', session_key: 'messenger:PAGE123:PSID123', output_mode: 'facebook', raw_body: '{"entry":[{"id":"PAGE123"}]}', signature: 'sha256=abc123' }],
});

const verifyMetaSignature = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Verify Meta Signature',
    position: [688, 560],
    parameters: {
      method: 'POST',
      url: expr(`{{ ${DJANGO_BASE_URL_EXPR} }}/messenger/meta/verify-signature/`),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { page_id: $json.page_id, raw_body: $json.raw_body, signature: $json.signature } }}'),
      options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 15000 },
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ verified: true }],
});

const routeMetaSignature = switchCase({
  version: 3.4,
  config: {
    name: 'Route Meta Signature',
    position: [912, 560],
    parameters: {
      mode: 'rules',
      rules: {
        values: [
          {
            renameOutput: true,
            outputKey: 'signature_verified',
            conditions: {
              options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
              conditions: [{ leftValue: expr('{{ $json.verified ? "true" : "false" }}'), rightValue: 'true', operator: { type: 'string', operation: 'equals' } }],
              combinator: 'and',
            },
          },
          {
            renameOutput: true,
            outputKey: 'signature_invalid',
            conditions: {
              options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
              conditions: [{ leftValue: expr('{{ $json.verified ? "true" : "false" }}'), rightValue: 'false', operator: { type: 'string', operation: 'equals' } }],
              combinator: 'and',
            },
          },
        ],
      },
      options: { fallbackOutput: 'none' },
    },
  },
});

const ignoreInvalidMetaSignature = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Ignore Invalid Meta Signature',
    position: [1136, 432],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: 'return [];',
    },
  },
  output: [],
});

const widgetAssistantWebhook = trigger({
  type: 'n8n-nodes-base.webhook',
  version: 2.1,
  config: {
    name: 'Widget Assistant Webhook',
    position: [240, 1040],
    parameters: {
      httpMethod: 'POST',
      path: 'kliniassist-widget-assistant',
      responseMode: 'responseNode',
      options: {},
    },
  },
  output: [{ body: { channel: 'widget', clinic_id: 1, clinic_slug: 'demo-clinic', message: 'Can I book tomorrow?', history: [], session_id: 'SESSION123' } }],
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
const message = String(body.message || body.text || '').trim();
const sessionId = String(body.session_id || body.sessionId || '').trim() || ('stateless:' + $execution.id);
return [{ json: {
  channel: 'widget',
  message,
  page_id: '',
  psid: '',
  clinic_slug: clinicSlug,
  clinic_id: body.clinic_id || body.clinicId || '',
  history: Array.isArray(body.history) ? body.history.slice(-10) : [],
  session_id: sessionId,
  session_key: 'widget:' + (clinicSlug || 'unknown-clinic') + ':' + sessionId,
  output_mode: 'widget_json'
} }];`,
    },
  },
  output: [{ channel: 'widget', message: 'Can I book tomorrow?', page_id: '', psid: '', clinic_slug: 'demo-clinic', clinic_id: 1, history: [], session_id: 'SESSION123', session_key: 'widget:demo-clinic:SESSION123', output_mode: 'widget_json' }],
});

const getMessengerClinicContext = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Get Messenger Clinic Context',
    position: [688, 560],
    parameters: {
      method: 'POST',
      url: expr(`{{ ${DJANGO_BASE_URL_EXPR} }}/messenger/ai/context/`),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { page_id: $("Normalize Messenger Request").item.json.page_id } }}'),
      options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 15000 },
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ found: true, page_id: 'PAGE123', page_token: 'PAGE_TOKEN', clinic: { id: 1, name: 'Demo Clinic', timezone: 'Asia/Manila' }, current_time: { timezone: 'Asia/Manila', now: '2026-06-01T09:00:00+08:00', today: '2026-06-01' }, ai: { is_ai_enabled: true, instructions: 'Be helpful.', fallback_message: MESSENGER_FALLBACK }, services: [], faqs: [] }],
});

const getWidgetClinicContext = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Get Widget Clinic Context',
    position: [688, 1040],
    parameters: {
      method: 'POST',
      url: expr(`{{ ${DJANGO_BASE_URL_EXPR} }}/messenger/ai/widget/context/`),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { clinic_slug: $json.clinic_slug } }}'),
      options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 15000 },
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ found: true, channel: 'widget', clinic: { id: 1, slug: 'demo-clinic', name: 'Demo Clinic', timezone: 'Asia/Manila' }, current_time: { timezone: 'Asia/Manila', now: '2026-06-01T09:00:00+08:00', today: '2026-06-01' }, ai: { is_ai_enabled: true, instructions: 'Be helpful.', fallback_message: WIDGET_FALLBACK }, services: [], faqs: [] }],
});

const buildMessengerSharedInput = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Build Messenger Shared Input',
    position: [912, 560],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const sources = $items('Normalize Messenger Request');
return $input.all().map((input, itemIndex) => {
  const context = input.json || {};
  const source = sources[itemIndex]?.json || {};
  const aiVersion = context.ai?.settings_updated_at || 'unversioned';
  return { json: { ...source, session_key: source.session_key + ':ai-settings:' + aiVersion, context, fallback_message: context.ai?.fallback_message || '${MESSENGER_FALLBACK}' } };
});`,
    },
  },
  output: [{ channel: 'messenger', message: 'Can I book cleaning tomorrow?', page_id: 'PAGE123', psid: 'PSID123', clinic_slug: '', session_key: 'messenger:PAGE123:PSID123', output_mode: 'facebook', fallback_message: MESSENGER_FALLBACK, context: { found: true, ai: { is_ai_enabled: true } } }],
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
const source = $items('Normalize Widget Request')[0].json || {};
const aiVersion = context.ai?.settings_updated_at || 'unversioned';
return [{ json: { ...source, session_key: source.session_key + ':ai-settings:' + aiVersion, context, fallback_message: context.ai?.fallback_message || '${WIDGET_FALLBACK}' } }];`,
    },
  },
  output: [{ channel: 'widget', message: 'Can I book tomorrow?', page_id: '', psid: '', clinic_slug: 'demo-clinic', session_id: 'SESSION123', session_key: 'widget:demo-clinic:SESSION123', output_mode: 'widget_json', fallback_message: WIDGET_FALLBACK, context: { found: true, ai: { is_ai_enabled: true } } }],
});

const sharedAiInput = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Shared AI Input',
    position: [1136, 800],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: 'return $input.all();',
    },
  },
  output: [{ channel: 'widget', message: 'Can I book tomorrow?', clinic_slug: 'demo-clinic', session_key: 'widget:demo-clinic:SESSION123', output_mode: 'widget_json', fallback_message: WIDGET_FALLBACK, context: { found: true, ai: { is_ai_enabled: true } } }],
});

const resolveAssistantMode = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Resolve Assistant Mode',
    position: [1360, 800],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `return $input.all().map((input) => {
  const item = input.json || {};
  const channel = item.channel || 'widget';
  const messengerMode = item.context?.ai?.messenger_response_mode || 'quick_replies';
  // Messenger must use messenger_response_mode. Widget keeps is_ai_enabled.
  const useAi = channel === 'messenger' ? messengerMode === 'ai' : item.context?.ai?.is_ai_enabled === true;
  const useQuickReplies = channel === 'messenger' && messengerMode !== 'ai';
  const assistantRoute = useAi ? 'ai' : (useQuickReplies ? 'quick_replies' : 'fallback');
  return { json: { ...item, messenger_response_mode: messengerMode, should_use_ai: useAi, should_use_quick_replies: useQuickReplies, assistant_route: assistantRoute } };
});`,
    },
  },
  output: [{ channel: 'messenger', messenger_response_mode: 'quick_replies', should_use_ai: false, should_use_quick_replies: true, assistant_route: 'quick_replies' }],
});

const routeAssistantMode = switchCase({
  version: 3.4,
  config: {
    name: 'Route Assistant Mode',
    position: [1488, 800],
    parameters: {
      mode: 'rules',
      rules: {
        values: [
          {
            renameOutput: true,
            outputKey: 'ai',
            conditions: {
              options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
              conditions: [{ leftValue: expr('{{ $json.assistant_route }}'), rightValue: 'ai', operator: { type: 'string', operation: 'equals' } }],
              combinator: 'and',
            },
          },
          {
            renameOutput: true,
            outputKey: 'quick_replies',
            conditions: {
              options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
              conditions: [{ leftValue: expr('{{ $json.assistant_route }}'), rightValue: 'quick_replies', operator: { type: 'string', operation: 'equals' } }],
              combinator: 'and',
            },
          },
          {
            renameOutput: true,
            outputKey: 'fallback',
            conditions: {
              options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
              conditions: [{ leftValue: expr('{{ $json.assistant_route }}'), rightValue: 'fallback', operator: { type: 'string', operation: 'equals' } }],
              combinator: 'and',
            },
          },
        ],
      },
      options: { fallbackOutput: 'none' },
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
      model: { __rl: true, value: 'deepseek-ai/DeepSeek-V4-Flash', mode: 'list', cachedResultName: 'deepseek-ai/DeepSeek-V4-Flash' },
      responsesApiEnabled: false,
      options: { temperature: 0.2 },
    },
    credentials: { openAiApi: newCredential('OpenAI account', 's8YZSke1JLPd3A2x') },
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
      sessionKey: expr('{{ $("Shared AI Input").item.json.session_key + ":shared:v4:" + ($("Shared AI Input").item.json.context?.ai?.settings_updated_at || "unversioned") }}'),
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
      url: expr(`{{ $("Shared AI Input").item.json.channel === "messenger" ? (${DJANGO_BASE_URL_EXPR} + "/messenger/ai/services/") : (${DJANGO_BASE_URL_EXPR} + "/messenger/ai/widget/services/") }}`),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
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
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
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
      url: expr(`{{ $("Shared AI Input").item.json.channel === "messenger" ? (${DJANGO_BASE_URL_EXPR} + "/messenger/ai/availability/") : (${DJANGO_BASE_URL_EXPR} + "/messenger/ai/widget/availability/") }}`),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
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
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
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
      url: expr(`{{ $("Shared AI Input").item.json.channel === "messenger" ? (${DJANGO_BASE_URL_EXPR} + "/messenger/ai/book/") : (${DJANGO_BASE_URL_EXPR} + "/messenger/ai/widget/book/") }}`),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: {
        page_id: expr('{{ $("Shared AI Input").item.json.channel === "messenger" ? $("Shared AI Input").item.json.page_id : "" }}'),
        clinic_slug: expr('{{ $("Shared AI Input").item.json.channel === "widget" ? $("Shared AI Input").item.json.clinic_slug : "" }}'),
        service_id: fromAi('service_id', 'Numeric service ID selected from clinic services'),
        starts_at: fromAi('starts_at', 'Confirmed appointment start time as clinic-local ISO 8601 datetime with timezone offset'),
        full_name: fromAi('full_name', 'Patient full name'),
        phone: fromAi('phone', 'Patient phone number'),
        email: fromAi('email', 'Patient email required for booking'),
        reason: fromAi('reason', 'Patient reason or notes if provided, otherwise blank'),
        confirmed: fromAi('confirmed', 'Boolean true only after the user explicitly confirms the summarized appointment'),
      },
      options: {},
      optimizeResponse: true,
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ created: false, error: 'Appointment creation requires explicit user confirmation.' }],
});

const findVerifiedAppointmentTool = tool({
  type: 'n8n-nodes-base.httpRequestTool',
  version: 4.4,
  config: {
    name: 'find_verified_appointment',
    position: [2176, 1040],
    parameters: {
      method: 'POST',
      url: expr(`{{ $("Shared AI Input").item.json.channel === "messenger" ? (${DJANGO_BASE_URL_EXPR} + "/messenger/ai/appointment/lookup/") : (${DJANGO_BASE_URL_EXPR} + "/messenger/ai/widget/appointment/lookup/") }}`),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: {
        page_id: expr('{{ $("Shared AI Input").item.json.channel === "messenger" ? $("Shared AI Input").item.json.page_id : "" }}'),
        clinic_slug: expr('{{ $("Shared AI Input").item.json.channel === "widget" ? $("Shared AI Input").item.json.clinic_slug : "" }}'),
        reference_code: fromAi('reference_code', 'Appointment reference code provided by the patient'),
        phone: fromAi('phone', 'Patient phone number for verification'),
      },
      options: {},
      optimizeResponse: true,
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ found: false, error: 'Appointment not found. Please check the reference code and phone number.' }],
});

const cancelVerifiedAppointmentTool = tool({
  type: 'n8n-nodes-base.httpRequestTool',
  version: 4.4,
  config: {
    name: 'cancel_verified_appointment',
    position: [2304, 1040],
    parameters: {
      method: 'POST',
      url: expr(`{{ $("Shared AI Input").item.json.channel === "messenger" ? (${DJANGO_BASE_URL_EXPR} + "/messenger/ai/appointment/cancel/") : (${DJANGO_BASE_URL_EXPR} + "/messenger/ai/widget/appointment/cancel/") }}`),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: {
        page_id: expr('{{ $("Shared AI Input").item.json.channel === "messenger" ? $("Shared AI Input").item.json.page_id : "" }}'),
        clinic_slug: expr('{{ $("Shared AI Input").item.json.channel === "widget" ? $("Shared AI Input").item.json.clinic_slug : "" }}'),
        reference_code: fromAi('reference_code', 'Appointment reference code provided by the patient'),
        phone: fromAi('phone', 'Patient phone number for verification'),
        confirmed: fromAi('confirmed', 'Boolean true only after the user explicitly confirms the cancellation summary'),
        reason: fromAi('reason', 'Cancellation reason if the patient provided one, otherwise blank'),
      },
      options: {},
      optimizeResponse: true,
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ cancelled: false, error: 'Appointment change requires explicit user confirmation.' }],
});

const rescheduleVerifiedAppointmentTool = tool({
  type: 'n8n-nodes-base.httpRequestTool',
  version: 4.4,
  config: {
    name: 'reschedule_verified_appointment',
    position: [2432, 1040],
    parameters: {
      method: 'POST',
      url: expr(`{{ $("Shared AI Input").item.json.channel === "messenger" ? (${DJANGO_BASE_URL_EXPR} + "/messenger/ai/appointment/reschedule/") : (${DJANGO_BASE_URL_EXPR} + "/messenger/ai/widget/appointment/reschedule/") }}`),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: {
        page_id: expr('{{ $("Shared AI Input").item.json.channel === "messenger" ? $("Shared AI Input").item.json.page_id : "" }}'),
        clinic_slug: expr('{{ $("Shared AI Input").item.json.channel === "widget" ? $("Shared AI Input").item.json.clinic_slug : "" }}'),
        reference_code: fromAi('reference_code', 'Appointment reference code provided by the patient'),
        phone: fromAi('phone', 'Patient phone number for verification'),
        starts_at: fromAi('starts_at', 'Confirmed new appointment start time as clinic-local ISO 8601 datetime with timezone offset'),
        confirmed: fromAi('confirmed', 'Boolean true only after the user explicitly confirms the reschedule summary'),
      },
      options: {},
      optimizeResponse: true,
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ rescheduled: false, error: 'Appointment change requires explicit user confirmation.' }],
});

const getMessengerQuickReplies = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Get Messenger Quick Replies',
    position: [1744, 520],
    parameters: {
      method: 'POST',
      url: expr(`{{ ${DJANGO_BASE_URL_EXPR} }}/messenger/n8n-webhook/`),
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { page_id: $json.page_id, psid: $json.psid, text: $json.message, postback: $json.postback || "" } }}'),
      options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 15000 },
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ replies: [{ type: 'quick_replies', text: 'Choose an option:', options: [{ title: 'Book an appointment', payload: 'start_booking' }] }], page_token: 'PAGE_TOKEN' }],
});

const prepareMessengerQuickReplies = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Prepare Messenger Quick Replies',
    position: [1968, 520],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const items = [];
for (const inputItem of $input.all()) {
  const input = inputItem.json || {};
  const actions = Array.isArray(input.replies) ? input.replies : [];
  const pageToken = input.page_token || '';
  const psid = input.psid || '';
  if (!pageToken || !psid) { continue; }
  for (const action of actions) {
    if (action.type === 'text') {
      items.push({ json: { access_token: pageToken, facebook_body: { messaging_type: 'RESPONSE', recipient: { id: psid }, message: { text: String(action.text || '') } } } });
    }
    if (action.type === 'quick_replies') {
      const quickReplies = (action.options || []).slice(0, 13).map((option) => ({ content_type: 'text', title: String(option.title || '').slice(0, 20), payload: String(option.payload || '') }));
      const message = { text: String(action.text || '') };
      if (quickReplies.length) { message.quick_replies = quickReplies; }
      items.push({ json: { access_token: pageToken, facebook_body: { messaging_type: 'RESPONSE', recipient: { id: psid }, message } } });
    }
  }
  if (!actions.length) {
    const fallback = input.fallback_message || '${MESSENGER_FALLBACK}';
    items.push({ json: { access_token: pageToken, facebook_body: { messaging_type: 'RESPONSE', recipient: { id: psid }, message: { text: fallback } } } });
  }
}
return items;`,
    },
  },
  output: [{ access_token: 'PAGE_TOKEN', facebook_body: { messaging_type: 'RESPONSE', recipient: { id: 'PSID123' }, message: { text: 'Choose an option:', quick_replies: [{ content_type: 'text', title: 'Book an appointment', payload: 'start_booking' }] } } }],
});

const kliniAssistSharedAiAgent = node({
  type: '@n8n/n8n-nodes-langchain.agent',
  version: 3.1,
  config: {
    name: 'KliniAssist Shared AI Agent',
    position: [1744, 720],
    parameters: {
      promptType: 'define',
      text: expr('{{ $("Shared AI Input").item.json.message }}'),
      options: {
        systemMessage: expr('KliniAssist shared Messenger and Widget assistant.\n\n' +
          'Clinic instructions:\n{{ $("Shared AI Input").item.json.context?.ai?.instructions || "No custom clinic instructions configured." }}\n\n' +
          'Channel: {{ $("Shared AI Input").item.json.channel }}\n' +
          'Clinic context JSON:\n{{ JSON.stringify($("Shared AI Input").item.json.context || {}) }}\n\n' +
          'Current clinic date/time:\n' +
          '- Timezone: {{ $("Shared AI Input").item.json.context?.current_time?.timezone || $("Shared AI Input").item.json.context?.clinic?.timezone || "UTC" }}\n' +
          '- Now: {{ $("Shared AI Input").item.json.context?.current_time?.now || $now.setZone($("Shared AI Input").item.json.context?.clinic?.timezone || "UTC").toISO() }}\n' +
          '- Today: {{ $("Shared AI Input").item.json.context?.current_time?.today || $now.setZone($("Shared AI Input").item.json.context?.clinic?.timezone || "UTC").toISODate() }}\n\n' +
          'Use match_services, check_availability, and book_confirmed_appointment for booking. Collect service, date/time, full name, phone, and email before booking. Ask for explicit confirmation before booking. Never expose secrets, invent clinic data, give medical diagnosis, or create appointments without tool validation. ' +
          'Use find_verified_appointment before canceling or rescheduling. Ask for appointment reference code and phone number before appointment management lookup. Summarize the verified appointment and requested action before mutation. Ask for explicit confirmation before canceling or rescheduling. Use cancel_verified_appointment and reschedule_verified_appointment only after explicit confirmation. Do not use user-supplied appointment IDs, patient IDs, clinic IDs, or service IDs for appointment management. ' +
          'Use check_availability suggestion_type metadata: nearest_time means the requested time is unavailable; next_available_date means the requested date has no slots. ' +
          'Use FAQ entries as clinic knowledge without citing the source. Do not say based on the FAQ, according to the FAQ, the FAQ says. ' +
          'Messenger replies must be plain concise text. Widget replies must be concise and friendly.'),
        maxIterations: 8,
        returnIntermediateSteps: false,
      },
    },
    subnodes: {
      model: sharedChatModel,
      memory: sharedConversationMemory,
      tools: [
        matchServicesTool,
        checkAvailabilityTool,
        bookConfirmedAppointmentTool,
        findVerifiedAppointmentTool,
        cancelVerifiedAppointmentTool,
        rescheduleVerifiedAppointmentTool,
      ],
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
      jsCode: `return $input.all().map((input) => {
  const item = input.json || {};
  const fallback = item.fallback_message || (item.channel === 'messenger' ? '${MESSENGER_FALLBACK}' : '${WIDGET_FALLBACK}');
  return { json: { output: fallback } };
});`,
    },
  },
  output: [{ output: WIDGET_FALLBACK }],
});

const prepareChannelReply = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Prepare Channel Reply',
    position: [2192, 800],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const sharedItems = $items('Shared AI Input');
return $input.all().map((inputItem, itemIndex) => {
  const input = inputItem.json || {};
  const shared = sharedItems[itemIndex]?.json || {};
  const context = shared.context || {};
  const channel = shared.channel || 'widget';
  const genericFallback = channel === 'messenger' ? '${MESSENGER_FALLBACK}' : '${WIDGET_FALLBACK}';
  let text = input.output || input.text || input.response || input.reply || shared.fallback_message || genericFallback;
  text = String(text).replace(/<think[\\s\\S]*?<\\/think>/gi, '').replace(/<\\/?think>/gi, '').trim();
  if (!text) {
    text = shared.fallback_message || genericFallback;
  }
  const maxLength = channel === 'messenger' ? 1900 : 1800;
  if (text.length > maxLength) {
    text = text.slice(0, maxLength);
  }
  return { json: {
    ...shared,
    reply_text: text,
    access_token: context.page_token || '',
    facebook_body: { messaging_type: 'RESPONSE', recipient: { id: shared.psid || '' }, message: { text } },
    widget_body: { reply: text }
  } };
});`,
    },
  },
  output: [{ channel: 'widget', reply_text: 'Assistant reply', access_token: '', facebook_body: { messaging_type: 'RESPONSE', recipient: { id: '' }, message: { text: 'Assistant reply' } }, widget_body: { reply: 'Assistant reply' } }],
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
              conditions: [{ leftValue: expr('{{ $json.channel }}'), rightValue: 'messenger', operator: { type: 'string', operation: 'equals' } }],
              combinator: 'and',
            },
          },
          {
            renameOutput: true,
            outputKey: 'widget',
            conditions: {
              options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
              conditions: [{ leftValue: expr('{{ $json.channel }}'), rightValue: 'widget', operator: { type: 'string', operation: 'equals' } }],
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
      queryParameters: { parameters: [{ name: 'access_token', value: expr('{{ $json.access_token }}') }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ $json.facebook_body }}'),
      options: { response: { response: { responseFormat: 'json' } }, timeout: 15000 },
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
        responseHeaders: { entries: [{ name: 'Content-Type', value: 'application/json' }] },
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
  .to(acknowledgeMetaMessengerEvent)
  .to(normalizeMessengerRequest)
  .to(verifyMetaSignature)
  .to(routeMetaSignature
    .onCase(0, getMessengerClinicContext
      .to(buildMessengerSharedInput)
      .to(sharedAiInput)
      .to(resolveAssistantMode)
      .to(routeAssistantMode
        .onCase(0, kliniAssistSharedAiAgent.to(prepareChannelReply).to(routeChannelReply
          .onCase(0, sendFacebookReply)
          .onCase(1, returnWidgetReply)))
        .onCase(1, getMessengerQuickReplies.to(prepareMessengerQuickReplies).to(sendFacebookReply))
        .onCase(2, prepareSharedFallback.to(prepareChannelReply).to(routeChannelReply
          .onCase(0, sendFacebookReply)
          .onCase(1, returnWidgetReply)))))
    .onCase(1, ignoreInvalidMetaSignature))
  .add(widgetAssistantWebhook)
  .to(normalizeWidgetRequest)
  .to(getWidgetClinicContext)
  .to(buildWidgetSharedInput)
  .to(sharedAiInput);
