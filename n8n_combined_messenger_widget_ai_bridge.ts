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
const N8N_WEBHOOK_CREDENTIAL_ID = 'replace-with-n8n-http-header-credential-id';
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
      path: 'clinicflow-messenger',
      responseMode: 'responseNode',
      options: {},
    },
  },
  output: [{ query: { 'hub.mode': 'subscribe', 'hub.challenge': '123456789' } }],
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
      path: 'clinicflow-messenger',
      responseMode: 'responseNode',
      options: {},
    },
  },
  output: [{ body: { entry: [{ id: 'PAGE123', messaging: [{ sender: { id: 'PSID123' }, recipient: { id: 'PAGE123' }, message: { text: 'Can I book cleaning tomorrow?' } }] }] } }],
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
  output: [{ body: { entry: [{ id: 'PAGE123', messaging: [{ sender: { id: 'PSID123' }, recipient: { id: 'PAGE123' }, message: { text: 'Can I book cleaning tomorrow?' } }] }] } }],
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
const message = String(messaging.message?.text || '').trim();
if (!pageId || !psid || !message) {
  return [];
}
return [{ json: {
  channel: 'messenger',
  message,
  page_id: pageId,
  psid,
  clinic_slug: '',
  session_id: '',
  session_key: 'messenger:' + pageId + ':' + psid,
  output_mode: 'facebook'
} }];`,
    },
  },
  output: [{ channel: 'messenger', message: 'Can I book cleaning tomorrow?', page_id: 'PAGE123', psid: 'PSID123', clinic_slug: '', session_id: '', session_key: 'messenger:PAGE123:PSID123', output_mode: 'facebook' }],
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
      url: `${DJANGO_BASE_URL}/messenger/ai/context/`,
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { page_id: $json.page_id } }}'),
      options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 15000 },
    },
    credentials: { httpHeaderAuth: newCredential('ClinicFlow N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
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
      url: `${DJANGO_BASE_URL}/messenger/ai/widget/context/`,
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { clinic_slug: $json.clinic_slug } }}'),
      options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 15000 },
    },
    credentials: { httpHeaderAuth: newCredential('ClinicFlow N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
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
      jsCode: `const context = $input.first().json || {};
const source = $items('Normalize Messenger Request')[0].json || {};
return [{ json: { ...source, context, fallback_message: context.ai?.fallback_message || '${MESSENGER_FALLBACK}' } }];`,
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
return [{ json: { ...source, context, fallback_message: context.ai?.fallback_message || '${WIDGET_FALLBACK}' } }];`,
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

const checkSharedAiEnabled = ifElse({
  version: 2.3,
  config: {
    name: 'Check Shared AI Enabled',
    position: [1360, 800],
    parameters: {
      conditions: {
        options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
        conditions: [
          { leftValue: expr('{{ $json.context?.found }}'), rightValue: true, operator: { type: 'boolean', operation: 'equals' } },
          { leftValue: expr('{{ $json.context?.ai?.is_ai_enabled }}'), rightValue: true, operator: { type: 'boolean', operation: 'equals' } },
          { leftValue: expr('{{ !!$json.message }}'), rightValue: true, operator: { type: 'boolean', operation: 'equals' } },
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
      url: expr('{{ $("Shared AI Input").item.json.channel === "messenger" ? "https://clinic.example.com/messenger/ai/services/" : "https://clinic.example.com/messenger/ai/widget/services/" }}'),
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
    credentials: { httpHeaderAuth: newCredential('ClinicFlow N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
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
      url: expr('{{ $("Shared AI Input").item.json.channel === "messenger" ? "https://clinic.example.com/messenger/ai/availability/" : "https://clinic.example.com/messenger/ai/widget/availability/" }}'),
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
    credentials: { httpHeaderAuth: newCredential('ClinicFlow N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
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
      url: expr('{{ $("Shared AI Input").item.json.channel === "messenger" ? "https://clinic.example.com/messenger/ai/book/" : "https://clinic.example.com/messenger/ai/widget/book/" }}'),
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
        email: fromAi('email', 'Patient email if provided, otherwise blank'),
        reason: fromAi('reason', 'Patient reason or notes if provided, otherwise blank'),
        confirmed: fromAi('confirmed', 'Boolean true only after the user explicitly confirms the summarized appointment'),
      },
      options: {},
      optimizeResponse: true,
    },
    credentials: { httpHeaderAuth: newCredential('ClinicFlow N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ created: false, error: 'Appointment creation requires explicit user confirmation.' }],
});

const clinicFlowSharedAiAgent = node({
  type: '@n8n/n8n-nodes-langchain.agent',
  version: 3.1,
  config: {
    name: 'ClinicFlow Shared AI Agent',
    position: [1744, 720],
    parameters: {
      promptType: 'define',
      text: expr('{{ $("Shared AI Input").item.json.message }}'),
      options: {
        systemMessage: expr('ClinicFlow shared Messenger and Widget assistant.\n\n' +
          'Clinic instructions:\n{{ $("Shared AI Input").item.json.context?.ai?.instructions || "No custom clinic instructions configured." }}\n\n' +
          'Channel: {{ $("Shared AI Input").item.json.channel }}\n' +
          'Clinic context JSON:\n{{ JSON.stringify($("Shared AI Input").item.json.context || {}) }}\n\n' +
          'Current clinic date/time:\n' +
          '- Timezone: {{ $("Shared AI Input").item.json.context?.current_time?.timezone || $("Shared AI Input").item.json.context?.clinic?.timezone || "UTC" }}\n' +
          '- Now: {{ $("Shared AI Input").item.json.context?.current_time?.now || $now.setZone($("Shared AI Input").item.json.context?.clinic?.timezone || "UTC").toISO() }}\n' +
          '- Today: {{ $("Shared AI Input").item.json.context?.current_time?.today || $now.setZone($("Shared AI Input").item.json.context?.clinic?.timezone || "UTC").toISODate() }}\n\n' +
          'Use match_services, check_availability, and book_confirmed_appointment for booking. Ask for explicit confirmation before booking. Never expose secrets, invent clinic data, give medical diagnosis, or create appointments without tool validation. Messenger replies must be plain concise text. Widget replies must be concise and friendly.'),
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
const fallback = item.fallback_message || (item.channel === 'messenger' ? '${MESSENGER_FALLBACK}' : '${WIDGET_FALLBACK}');
return [{ json: { output: fallback } }];`,
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
      jsCode: `const input = $input.first().json || {};
const shared = $items('Shared AI Input')[0].json || {};
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
return [{ json: {
  ...shared,
  reply_text: text,
  access_token: context.page_token || '',
  facebook_body: { recipient: { id: shared.psid || '' }, message: { text } },
  widget_body: { reply: text }
} }];`,
    },
  },
  output: [{ channel: 'widget', reply_text: 'Assistant reply', access_token: '', facebook_body: { recipient: { id: '' }, message: { text: 'Assistant reply' } }, widget_body: { reply: 'Assistant reply' } }],
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
      options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 15000 },
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

export default workflow('ZTBqwEzdll6TZsUU', 'ClinicFlow Messenger + Widget AI Bridge')
  .add(metaWebhookVerification)
  .to(verifyMetaChallenge)
  .to(returnVerificationResponse)
  .add(metaMessengerEvents)
  .to(acknowledgeMetaMessengerEvent)
  .to(normalizeMessengerRequest)
  .to(getMessengerClinicContext)
  .to(buildMessengerSharedInput)
  .to(sharedAiInput)
  .to(checkSharedAiEnabled
    .onTrue(clinicFlowSharedAiAgent.to(prepareChannelReply).to(routeChannelReply
      .onCase(0, sendFacebookReply)
      .onCase(1, returnWidgetReply)))
    .onFalse(prepareSharedFallback.to(prepareChannelReply).to(routeChannelReply
      .onCase(0, sendFacebookReply)
      .onCase(1, returnWidgetReply))))
  .add(widgetAssistantWebhook)
  .to(normalizeWidgetRequest)
  .to(getWidgetClinicContext)
  .to(buildWidgetSharedInput)
  .to(sharedAiInput);
