import {
  workflow,
  node,
  trigger,
  switchCase,
  newCredential,
  expr,
} from '@n8n/workflow-sdk';

const DJANGO_BASE_URL_FALLBACK = 'https://178-105-83-211.nip.io';
const DJANGO_BASE_URL_EXPR = '($vars.DJANGO_BASE_URL || "' + DJANGO_BASE_URL_FALLBACK + '").replace(/\\/$/, "")';
const N8N_WEBHOOK_CREDENTIAL_ID = 'PJHqVMwE3qU58s9E';
const MESSENGER_FALLBACK = 'Thanks for your message. Please contact the clinic directly for help.';
const WIDGET_FALLBACK = 'Sorry, the assistant is unavailable right now. You can still book an appointment using the booking form.';
const DJANGO_MESSENGER_WEBHOOK_URL_EXPR = expr('{{ ' + DJANGO_BASE_URL_EXPR + ' + "/messenger/webhook/" }}');
const DJANGO_META_SIGNATURE_VERIFY_URL_EXPR = expr('{{ ' + DJANGO_BASE_URL_EXPR + ' + "/messenger/meta/verify-signature/" }}');
const DJANGO_MESSENGER_AI_CONTEXT_URL_EXPR = expr('{{ ' + DJANGO_BASE_URL_EXPR + ' + "/messenger/ai/context/" }}');
const DJANGO_AI_GATEWAY_REPLY_URL_EXPR = expr('{{ ' + DJANGO_BASE_URL_EXPR + ' + "/messenger/ai/gateway/reply/" }}');
const DJANGO_WIDGET_AI_CONTEXT_URL_EXPR = expr('{{ ' + DJANGO_BASE_URL_EXPR + ' + "/messenger/ai/widget/context/" }}');
const DJANGO_MESSENGER_AI_TURN_REGISTER_URL_EXPR = expr('{{ ' + DJANGO_BASE_URL_EXPR + ' + "/messenger/ai/turn/register/" }}');
const DJANGO_MESSENGER_AI_TURN_CLAIM_URL_EXPR = expr('{{ ' + DJANGO_BASE_URL_EXPR + ' + "/messenger/ai/turn/claim/" }}');
const DJANGO_MESSENGER_AI_TURN_COMPLETE_URL_EXPR = expr('{{ ' + DJANGO_BASE_URL_EXPR + ' + "/messenger/ai/turn/complete/" }}');
const DJANGO_MESSENGER_N8N_WEBHOOK_URL_EXPR = expr('{{ ' + DJANGO_BASE_URL_EXPR + ' + "/messenger/n8n-webhook/" }}');

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
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Verify Meta Challenge',
    position: [464, 160],
    parameters: {
      method: 'GET',
      url: DJANGO_MESSENGER_WEBHOOK_URL_EXPR,
      sendQuery: true,
      queryParameters: {
        parameters: [
          { name: 'hub.mode', value: expr('{{ $json.query["hub.mode"] || "" }}') },
          { name: 'hub.verify_token', value: expr('{{ $json.query["hub.verify_token"] || "" }}') },
          { name: 'hub.challenge', value: expr('{{ $json.query["hub.challenge"] || "" }}') },
        ],
      },
      options: { response: { response: { fullResponse: true, neverError: true, responseFormat: 'text' } }, timeout: 15000 },
    },
  },
  output: [{ statusCode: 200, data: '123456789' }],
});

const returnVerificationResponse = node({
  type: 'n8n-nodes-base.respondToWebhook',
  version: 1.5,
  config: {
    name: 'Return Verification Response',
    position: [688, 160],
    parameters: {
      respondWith: 'text',
      responseBody: expr('{{ $json.data || $json.body || "Invalid verification request" }}'),
      options: {
        responseCode: expr('{{ $json.statusCode || 403 }}'),
        responseHeaders: { entries: [{ name: 'Content-Type', value: 'text/plain' }] },
      },
    },
  },
  output: [{ data: '123456789' }],
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
    body = {};
  }
}
if (!rawBody && body && typeof body === 'object') {
  rawBody = JSON.stringify(body);
}
const headers = input.headers || {};
const signature = String(headers['X-Hub-Signature-256'] || headers['x-hub-signature-256'] || '').trim();
const entries = Array.isArray(body.entry) ? body.entry : [];
const items = [];
const ignoredCandidates = [];
for (const entry of entries) {
  const messagingItems = Array.isArray(entry.messaging) ? entry.messaging : [];
  if (!messagingItems.length && entry.id) {
    ignoredCandidates.push({ page_id: String(entry.id).trim(), psid: '' });
  }
  for (const messaging of messagingItems) {
    const pageId = String(entry.id || messaging.recipient?.id || '').trim();
    const psid = String(messaging.sender?.id || '').trim();
    const message = String(messaging.message?.text || '').trim();
    const postback = String(messaging.postback?.payload || messaging.message?.quick_reply?.payload || '').trim();
    const messageId = String(messaging.message?.mid || messaging.postback?.mid || '').trim();
    if (pageId && (!message && !postback)) {
      ignoredCandidates.push({ page_id: pageId, psid });
      continue;
    }
    if (!pageId || !psid || (!message && !postback)) {
      continue;
    }
    items.push({ json: {
      channel: 'messenger',
      message,
      postback,
      page_id: pageId,
      psid,
      message_id: messageId,
      clinic_slug: '',
      session_id: '',
      session_key: 'messenger:' + pageId + ':' + psid,
      output_mode: 'facebook',
      ignored_event: false,
      raw_body: rawBody,
      signature
    } });
  }
}
if (!items.length) {
  const ignored = ignoredCandidates[0] || {};
  const pageId = ignored.page_id || '';
  const psid = ignored.psid || '';
  items.push({ json: {
    channel: 'messenger',
    message: '',
    postback: '',
    page_id: pageId,
    psid,
    message_id: '',
    clinic_slug: '',
    session_id: '',
    session_key: 'messenger:' + (pageId || 'unknown-page') + ':' + (psid || 'ignored-event'),
    output_mode: 'facebook',
    ignored_event: true,
    raw_body: rawBody,
    signature
  } });
}
return items;`,
    },
  },
  output: [{ channel: 'messenger', message: 'Can I book cleaning tomorrow?', postback: '', page_id: 'PAGE123', psid: 'PSID123', message_id: 'mid.123', clinic_slug: '', session_id: '', session_key: 'messenger:PAGE123:PSID123', output_mode: 'facebook', ignored_event: false, raw_body: '{"entry":[{"id":"PAGE123"}]}', signature: 'sha256=abc123' }],
});

const verifyMetaSignature = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Verify Meta Signature',
    position: [688, 560],
    parameters: {
      method: 'POST',
      url: DJANGO_META_SIGNATURE_VERIFY_URL_EXPR,
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { page_id: $json.page_id, raw_body: $json.raw_body, signature: $json.signature, psid: $json.psid, message_id: $json.message_id } }}'),
      options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 15000 },
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ verified: true, duplicate: false }],
});

const prepareMetaWebhookResponse = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Prepare Meta Webhook Response',
    position: [912, 560],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const normalizedItems = $items('Normalize Messenger Request');
const verifiedItems = $input.all();
let hasInvalidSignature = false;
const processableEvents = [];
for (const [itemIndex, verifiedItem] of verifiedItems.entries()) {
  const verification = verifiedItem.json || {};
  const source = normalizedItems[itemIndex]?.json || {};
  const verified = verification.verified === true;
  const duplicate = verification.duplicate === true;
  const ignored_event = source.ignored_event === true;
  if (!verified) { hasInvalidSignature = true; }
  if (verified && !duplicate && !ignored_event) {
    processableEvents.push({ ...source, ...verification, duplicate, ignored_event });
  }
}
return [{ json: { response_route: hasInvalidSignature ? 'invalid_signature' : 'acknowledge', processable_events: processableEvents } }];`,
    },
  },
  output: [{ response_route: 'acknowledge', processable_events: [] }],
});

const routeMetaWebhookResponse = switchCase({
  version: 3.4,
  config: {
    name: 'Route Meta Webhook Response',
    position: [1136, 560],
    parameters: {
      mode: 'rules',
      rules: {
        values: [
          {
            renameOutput: true,
            outputKey: 'acknowledge',
            conditions: {
              options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
              conditions: [{ leftValue: expr('{{ $json.response_route }}'), rightValue: 'acknowledge', operator: { type: 'string', operation: 'equals' } }],
              combinator: 'and',
            },
          },
          {
            renameOutput: true,
            outputKey: 'invalid_signature',
            conditions: {
              options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
              conditions: [{ leftValue: expr('{{ $json.response_route }}'), rightValue: 'invalid_signature', operator: { type: 'string', operation: 'equals' } }],
              combinator: 'and',
            },
          },
        ],
      },
      options: { fallbackOutput: 'none' },
    },
  },
});

const acknowledgeMetaMessengerEvent = node({
  type: 'n8n-nodes-base.respondToWebhook',
  version: 1.5,
  config: {
    name: 'Acknowledge Meta Messenger Event',
    position: [1360, 560],
    parameters: {
      respondWith: 'text',
      responseBody: 'EVENT_RECEIVED',
      options: {
        responseCode: 200,
        responseHeaders: { entries: [{ name: 'Content-Type', value: 'text/plain' }] },
      },
    },
  },
  output: [{ response_route: 'acknowledge', processable_events: [{ channel: 'messenger', page_id: 'PAGE123', psid: 'PSID123', message_id: 'mid.123', message: 'Hello', postback: '', raw_body: '{}', signature: 'sha256=abc123', verified: true, duplicate: false, ignored_event: false }] }],
});

const returnInvalidMetaSignature = node({
  type: 'n8n-nodes-base.respondToWebhook',
  version: 1.5,
  config: {
    name: 'Return Invalid Meta Signature',
    position: [1360, 432],
    parameters: {
      respondWith: 'text',
      responseBody: 'Invalid signature',
      options: {
        responseCode: 403,
        responseHeaders: { entries: [{ name: 'Content-Type', value: 'text/plain' }] },
      },
    },
  },
  output: [{ response_route: 'invalid_signature' }],
});

const expandMessengerProcessableEvents = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Expand Messenger Processable Events',
    position: [1584, 560],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const input = $input.first().json || {};
const events = Array.isArray(input.processable_events) ? input.processable_events : [];
return events.map((event) => ({ json: event }));`,
    },
  },
  output: [{ channel: 'messenger', page_id: 'PAGE123', psid: 'PSID123', message_id: 'mid.123', message: 'Hello', postback: '', raw_body: '{}', signature: 'sha256=abc123', verified: true, duplicate: false, ignored_event: false }],
});

const registerMessengerTurn = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Register Messenger Turn',
    position: [1808, 560],
    parameters: {
      method: 'POST',
      url: DJANGO_MESSENGER_AI_TURN_REGISTER_URL_EXPR,
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { page_id: $json.page_id, psid: $json.psid, message_id: $json.message_id, message: $json.message, postback: $json.postback || "" } }}'),
      options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 15000 },
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ registered: true, duplicate: false, process_now: true, superseded_previous: false, turn_token: 'turn-token', input_sequence: 1, messages: [{ sequence: 1, text: 'June 15', postback: '' }], message: 'New Messenger messages in order:\n- June 15' }],
});

const attachMessengerTurnRegistration = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Attach Messenger Turn Registration',
    position: [1968, 560],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const sourceItems = $items('Expand Messenger Processable Events');
return $input.all().map((inputItem, itemIndex) => {
  const source = sourceItems[itemIndex]?.json || {};
  const registration = inputItem.json || {};
  const messages = Array.isArray(registration.messages) ? registration.messages : [];
  return { json: {
    ...source,
    raw_message: source.message || '',
    raw_postback: source.postback || '',
    registration,
    registered: registration.registered === true,
    duplicate: registration.duplicate === true,
    process_now: registration.process_now === true,
    superseded_previous: registration.superseded_previous === true,
    turn_token: registration.turn_token || '',
    input_sequence: registration.input_sequence || 0,
    turn_messages: messages,
    message: registration.message || source.message || ''
  } };
});`,
    },
  },
  output: [{ channel: 'messenger', page_id: 'PAGE123', psid: 'PSID123', message: 'New Messenger messages in order:\n- June 15', raw_message: 'June 15', raw_postback: '', turn_token: 'turn-token', input_sequence: 1, process_now: true }],
});

const routeMessengerTurnRegistration = switchCase({
  version: 3.4,
  config: {
    name: 'Route Messenger Turn Registration',
    position: [2192, 560],
    parameters: {
      mode: 'rules',
      rules: {
        values: [
          {
            renameOutput: true,
            outputKey: 'process_now',
            conditions: {
              options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
              conditions: [{ leftValue: expr('{{ $json.process_now ? "true" : "false" }}'), rightValue: 'true', operator: { type: 'string', operation: 'equals' } }],
              combinator: 'and',
            },
          },
        ],
      },
      options: { fallbackOutput: 'none' },
    },
  },
});

const claimMessengerTurn = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Claim Messenger Turn',
    position: [2416, 560],
    parameters: {
      method: 'POST',
      url: DJANGO_MESSENGER_AI_TURN_CLAIM_URL_EXPR,
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { page_id: $json.page_id, psid: $json.psid, turn_token: $json.turn_token || "" } }}'),
      options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 15000 },
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ claimed: true, stale: false, turn_token: 'turn-token', input_sequence: 2, messages: [{ sequence: 1, text: 'June 15', postback: '' }, { sequence: 2, text: 'Cleaning', postback: '' }], message: 'New Messenger messages in order:\n- June 15\n- Cleaning', history: [] }],
});

const attachMessengerTurnClaim = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Attach Messenger Turn Claim',
    position: [2640, 560],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const sourceItems = $items('Route Messenger Turn Registration', 0);
return $input.all().map((inputItem, itemIndex) => {
  const source = sourceItems[itemIndex]?.json || {};
  const claim = inputItem.json || {};
  const messages = Array.isArray(claim.messages) ? claim.messages : (Array.isArray(source.turn_messages) ? source.turn_messages : []);
  const latestMessage = messages.length ? messages[messages.length - 1] : {};
  return { json: {
    ...source,
    claim,
    claimed: claim.claimed === true,
    stale: claim.stale === true,
    has_pending: claim.has_pending === true,
    turn_token: claim.turn_token || source.turn_token || '',
    input_sequence: claim.input_sequence || source.input_sequence || 0,
    turn_messages: messages,
    history: Array.isArray(claim.history) ? claim.history : [],
    message: claim.message || source.message || '',
    raw_message: source.raw_message || latestMessage.text || '',
    raw_postback: source.raw_postback || latestMessage.postback || ''
  } };
});`,
    },
  },
  output: [{ channel: 'messenger', page_id: 'PAGE123', psid: 'PSID123', message: 'New Messenger messages in order:\n- June 15\n- Cleaning', raw_message: 'Cleaning', raw_postback: '', turn_token: 'turn-token', input_sequence: 2, claimed: true }],
});

const routeMessengerTurnClaim = switchCase({
  version: 3.4,
  config: {
    name: 'Route Messenger Turn Claim',
    position: [2864, 560],
    parameters: {
      mode: 'rules',
      rules: {
        values: [
          {
            renameOutput: true,
            outputKey: 'claimed',
            conditions: {
              options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
              conditions: [{ leftValue: expr('{{ $json.claimed ? "true" : "false" }}'), rightValue: 'true', operator: { type: 'string', operation: 'equals' } }],
              combinator: 'and',
            },
          },
        ],
      },
      options: { fallbackOutput: 'none' },
    },
  },
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
      authentication: 'headerAuth',
      responseMode: 'responseNode',
      options: {},
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
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
    position: [3088, 560],
    parameters: {
      method: 'POST',
      url: DJANGO_MESSENGER_AI_CONTEXT_URL_EXPR,
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { page_id: $json.page_id } }}'),
      options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 15000 },
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ found: true, page_id: 'PAGE123', page_token: 'PAGE_TOKEN', clinic: { id: 1, name: 'Demo Clinic', timezone: 'Asia/Manila' }, current_time: { timezone: 'Asia/Manila', now: '2026-06-01T09:00:00+08:00', today: '2026-06-01' }, ai: { is_ai_enabled: true, instructions: 'Be helpful.', fallback_message: MESSENGER_FALLBACK }, services: [], faqs: [] }],
});

const attachMessengerContext = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Attach Messenger Context',
    position: [3312, 560],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const sourceItems = $items('Route Messenger Turn Claim', 0);
return $input.all().map((inputItem, itemIndex) => {
  const source = sourceItems[itemIndex]?.json || {};
  const context = inputItem.json || {};
  return { json: {
    ...source,
    context,
    access_token: context.page_token || ''
  } };
});`,
    },
  },
  output: [{ channel: 'messenger', page_id: 'PAGE123', psid: 'PSID123', message: 'New Messenger messages in order:\n- June 15\n- Cleaning', raw_message: 'Cleaning', raw_postback: '', turn_token: 'turn-token', input_sequence: 2, access_token: 'PAGE_TOKEN', context: { found: true, ai: { is_ai_enabled: true } } }],
});

const getWidgetClinicContext = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Get Widget Clinic Context',
    position: [688, 1040],
    parameters: {
      method: 'POST',
      url: DJANGO_WIDGET_AI_CONTEXT_URL_EXPR,
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
    position: [3536, 560],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `return $input.all().map((inputItem) => {
  const input = inputItem.json || {};
  const rawContext = input.context || {};
  const { page_token: pageToken, page_token_available: pageTokenAvailable, ...safeContext } = rawContext;
  const claim = input.claim || {};
  const aiVersion = safeContext.ai?.settings_updated_at || 'unversioned';
  return { json: { ...input, message: claim.message || input.message || '', turn_token: claim.turn_token || input.turn_token || '', input_sequence: claim.input_sequence || input.input_sequence || 0, turn_messages: claim.messages || input.turn_messages || [], history: claim.history || input.history || [], session_key: input.session_key + ':ai-settings:' + aiVersion + ':turn:' + (claim.turn_token || input.turn_token || 'no-turn'), access_token: pageToken || input.access_token || '', context: safeContext, fallback_message: safeContext.ai?.fallback_message || '${MESSENGER_FALLBACK}' } };
});`,
    },
  },
  output: [{ channel: 'messenger', message: 'Can I book cleaning tomorrow?', page_id: 'PAGE123', psid: 'PSID123', clinic_slug: '', session_key: 'messenger:PAGE123:PSID123', output_mode: 'facebook', access_token: 'PAGE_TOKEN', fallback_message: MESSENGER_FALLBACK, context: { found: true, ai: { is_ai_enabled: true } } }],
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

const getMessengerQuickReplies = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Get Messenger Quick Replies',
    position: [1744, 520],
    parameters: {
      method: 'POST',
      url: DJANGO_MESSENGER_N8N_WEBHOOK_URL_EXPR,
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { page_id: $json.page_id, psid: $json.psid, text: $json.raw_message || $json.message, postback: $json.raw_postback || $json.postback || "", turn_token: $json.turn_token || "", input_sequence: $json.input_sequence || 0 } }}'),
      options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 15000 },
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ replies: [{ type: 'quick_replies', text: 'Choose an option:', options: [{ title: 'Book an appointment', payload: 'start_booking' }] }], page_token: 'PAGE_TOKEN' }],
});

const attachMessengerQuickRepliesInput = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Attach Messenger Quick Replies Input',
    position: [1968, 520],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const sourceItems = $items('Route Assistant Mode', 1);
return $input.all().map((inputItem, itemIndex) => {
  const source = sourceItems[itemIndex]?.json || {};
  const response = inputItem.json || {};
  return { json: {
    ...source,
    quick_reply_response: response,
    replies: Array.isArray(response.replies) ? response.replies : [],
    page_token: response.page_token || source.access_token || '',
    access_token: response.page_token || source.access_token || ''
  } };
});`,
    },
  },
  output: [{ channel: 'messenger', page_id: 'PAGE123', psid: 'PSID123', turn_token: 'turn-token', input_sequence: 2, page_token: 'PAGE_TOKEN', access_token: 'PAGE_TOKEN', replies: [{ type: 'quick_replies', text: 'Choose an option:', options: [{ title: 'Book an appointment', payload: 'start_booking' }] }] }],
});

const prepareMessengerQuickReplies = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Prepare Messenger Quick Replies',
    position: [2192, 520],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const items = [];
const replyItems = $items('Attach Messenger Quick Replies Input');
for (const [itemIndex, inputItem] of $input.all().entries()) {
  const completion = inputItem.json || {};
  if (completion.send_reply === false) { continue; }
  const input = replyItems[itemIndex]?.json || {};
  const actions = Array.isArray(input.replies) ? input.replies : [];
  const pageToken = input.page_token || input.access_token || '';
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

const callDjangoAiGateway = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Call Django AI Gateway',
    position: [1744, 720],
    parameters: {
      method: 'POST',
      url: DJANGO_AI_GATEWAY_REPLY_URL_EXPR,
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { channel: $json.channel, page_id: $json.page_id || "", psid: $json.psid || "", turn_token: $json.turn_token || "", input_sequence: $json.input_sequence || 0, clinic_slug: $json.clinic_slug || "", message: $json.message || "", history: $json.history || [], context: $json.context || {} } }}'),
      options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 30000 },
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ reply: 'Assistant reply', fallback: false, error: '' }],
});

const attachDjangoAiGatewayInput = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Attach Django AI Gateway Input',
    position: [1968, 720],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const sourceItems = $items('Route Assistant Mode', 0);
return $input.all().map((inputItem, itemIndex) => {
  const source = sourceItems[itemIndex]?.json || {};
  const gateway = inputItem.json || {};
  return { json: { ...source, gateway_response: gateway, ...gateway } };
});`,
    },
  },
  output: [{ channel: 'messenger', page_id: 'PAGE123', psid: 'PSID123', access_token: 'PAGE_TOKEN', reply: 'Assistant reply', fallback: false, error: '' }],
});

const resolveDjangoAiGatewayRoute = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Resolve Django AI Gateway Route',
    position: [2080, 720],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const providerFallbackErrors = new Set(['ai_provider_unconfigured', 'ai_provider_error', 'empty_provider_reply', 'tool_loop_exceeded']);
return $input.all().map((inputItem) => {
  const item = inputItem.json || {};
  const error = String(item.error || '').trim();
  const providerFallback = item.channel === 'messenger' && item.fallback === true && providerFallbackErrors.has(error);
  return { json: { ...item, ai_gateway_route: providerFallback ? 'forced_quick_replies' : 'channel_reply', force_quick_replies: providerFallback } };
});`,
    },
  },
  output: [{ channel: 'messenger', page_id: 'PAGE123', psid: 'PSID123', force_quick_replies: true, ai_gateway_route: 'forced_quick_replies', fallback: true, error: 'ai_provider_unconfigured' }],
});

const routeDjangoAiGatewayResponse = switchCase({
  version: 3.4,
  config: {
    name: 'Route Django AI Gateway Response',
    position: [2192, 720],
    parameters: {
      mode: 'rules',
      rules: {
        values: [
          {
            renameOutput: true,
            outputKey: 'forced_quick_replies',
            conditions: {
              options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
              conditions: [{ leftValue: expr('{{ $json.ai_gateway_route }}'), rightValue: 'forced_quick_replies', operator: { type: 'string', operation: 'equals' } }],
              combinator: 'and',
            },
          },
          {
            renameOutput: true,
            outputKey: 'channel_reply',
            conditions: {
              options: { caseSensitive: true, leftValue: '', typeValidation: 'strict', version: 2 },
              conditions: [{ leftValue: expr('{{ $json.ai_gateway_route }}'), rightValue: 'channel_reply', operator: { type: 'string', operation: 'equals' } }],
              combinator: 'and',
            },
          },
        ],
      },
      options: { fallbackOutput: 'none' },
    },
  },
});

const getForcedMessengerQuickReplies = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Get Forced Messenger Quick Replies',
    position: [2416, 520],
    parameters: {
      method: 'POST',
      url: DJANGO_MESSENGER_N8N_WEBHOOK_URL_EXPR,
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { page_id: $json.page_id, psid: $json.psid, text: $json.raw_message || $json.message, postback: $json.raw_postback || $json.postback || "", turn_token: $json.turn_token || "", input_sequence: $json.input_sequence || 0, force_quick_replies: true } }}'),
      options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 15000 },
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ replies: [{ type: 'quick_replies', text: 'Choose an option:', options: [{ title: 'Book an appointment', payload: 'start_booking' }] }], page_token: 'PAGE_TOKEN' }],
});

const attachForcedMessengerQuickRepliesInput = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Attach Forced Messenger Quick Replies Input',
    position: [2640, 520],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const sourceItems = $items('Route Django AI Gateway Response', 0);
return $input.all().map((inputItem, itemIndex) => {
  const source = sourceItems[itemIndex]?.json || {};
  const response = inputItem.json || {};
  return { json: {
    ...source,
    quick_reply_response: response,
    replies: Array.isArray(response.replies) ? response.replies : [],
    page_token: response.page_token || source.access_token || '',
    access_token: response.page_token || source.access_token || ''
  } };
});`,
    },
  },
  output: [{ channel: 'messenger', page_id: 'PAGE123', psid: 'PSID123', turn_token: 'turn-token', input_sequence: 2, page_token: 'PAGE_TOKEN', access_token: 'PAGE_TOKEN', replies: [{ type: 'quick_replies', text: 'Choose an option:', options: [{ title: 'Book an appointment', payload: 'start_booking' }] }] }],
});

const completeForcedMessengerQuickReplyTurn = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Complete Forced Messenger Quick Reply Turn',
    position: [2864, 520],
    parameters: {
      method: 'POST',
      url: DJANGO_MESSENGER_AI_TURN_COMPLETE_URL_EXPR,
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { page_id: $json.page_id, psid: $json.psid, turn_token: $json.turn_token, input_sequence: $json.input_sequence || 0, reply_text: (($json.replies || []).map((reply) => reply.text || "").filter(Boolean).join("\\n")) } }}'),
      options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 15000 },
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ send_reply: true, stale: false, has_pending: false }],
});

const prepareForcedMessengerQuickReplies = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Prepare Forced Messenger Quick Replies',
    position: [3088, 520],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const items = [];
const replyItems = $items('Attach Forced Messenger Quick Replies Input');
for (const [itemIndex, inputItem] of $input.all().entries()) {
  const completion = inputItem.json || {};
  if (completion.send_reply === false) { continue; }
  const input = replyItems[itemIndex]?.json || {};
  const actions = Array.isArray(input.replies) ? input.replies : [];
  const pageToken = input.page_token || input.access_token || '';
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

const prepareSharedFallback = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Prepare Shared Fallback',
    position: [1600, 912],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `return $input.all().map((inputItem) => {
  const item = inputItem.json || {};
  const fallback = item.fallback_message || (item.channel === 'messenger' ? '${MESSENGER_FALLBACK}' : '${WIDGET_FALLBACK}');
  return { json: { ...item, output: fallback } };
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
      jsCode: `function redactPhoneLikeText(value) {
  return String(value || '').replace(/\\+?\\d[\\d\\s().-]{7,}\\d/g, (match) => {
    const digits = match.replace(/\\D/g, '');
    return digits.length >= 9 ? '[phone redacted]' : match;
  });
}
function isFailedAppointmentVerificationReply(value) {
  const text = String(value || '').toLowerCase();
  const appointmentContext = ['appointment', 'booking', 'reference', 'cancel', 'reschedul'].some((term) => text.includes(term));
  const identityContext = ['phone', 'number', 'verify', 'verification', 'unable to verify', "couldn't verify", 'could not verify', "doesn't match", 'does not match', 'not match', 'booked under', 'belongs to', 'provided', 'confirm', 'lookup', 'not found'].some((term) => text.includes(term));
  return appointmentContext && identityContext;
}
function stripAssistantReasoningText(value) {
  const original = String(value || '').trim();
  const paragraphs = original.split(/\\n\\s*\\n/).map((paragraph) => paragraph.trim()).filter(Boolean);
  if (paragraphs.length < 2) { return original; }
  const reasoningPatterns = [
    /^let me (check|think|look|analy[sz]e)\\b/i,
    /\\bthe user (wants|is asking|asked|provided|needs)\\b/i,
    /^wait\\b/i,
    /\\bi.?ll let the user know\\b/i,
    /\\bi need to (check|call|look)\\b.*\\b(availability|tool|details|first)\\b/i,
    /\\bi should (check|call|look|ask)\\b.*\\b(user|tool|availability|details)\\b/i,
  ];
  let firstPublicIndex = 0;
  while (firstPublicIndex < paragraphs.length - 1 && reasoningPatterns.some((pattern) => pattern.test(paragraphs[firstPublicIndex]))) {
    firstPublicIndex += 1;
  }
  return paragraphs.slice(firstPublicIndex).join('\\n\\n');
}
return $input.all().map((inputItem) => {
  const shared = inputItem.json || {};
  const context = shared.context || {};
  const channel = shared.channel || 'widget';
  const genericFallback = channel === 'messenger' ? '${MESSENGER_FALLBACK}' : '${WIDGET_FALLBACK}';
  let text = shared.output || shared.text || shared.response || shared.reply || shared.fallback_message || genericFallback;
  text = String(text).replace(/<think[\\s\\S]*?<\\/think>/gi, '').replace(/<\\/?think>/gi, '').trim();
  text = stripAssistantReasoningText(text);
  if (!text) {
    text = shared.fallback_message || genericFallback;
  }
  if (isFailedAppointmentVerificationReply(text)) {
    text = redactPhoneLikeText(text);
  }
  const maxLength = channel === 'messenger' ? 1900 : 1800;
  if (text.length > maxLength) {
    text = text.slice(0, maxLength);
  }
  return { json: {
    ...shared,
    reply_text: text,
    access_token: shared.access_token || '',
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

const completeMessengerTurn = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Complete Messenger Turn',
    position: [2640, 640],
    parameters: {
      method: 'POST',
      url: DJANGO_MESSENGER_AI_TURN_COMPLETE_URL_EXPR,
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { page_id: $json.page_id, psid: $json.psid, turn_token: $json.turn_token, input_sequence: $json.input_sequence, reply_text: $json.reply_text || "" } }}'),
      options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 15000 },
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ send_reply: true, stale: false, has_pending: false }],
});

const completeMessengerQuickReplyTurn = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Complete Messenger Quick Reply Turn',
    position: [1968, 520],
    parameters: {
      method: 'POST',
      url: DJANGO_MESSENGER_AI_TURN_COMPLETE_URL_EXPR,
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { page_id: $json.page_id, psid: $json.psid, turn_token: $json.turn_token, input_sequence: $json.input_sequence || 0, reply_text: (($json.replies || []).map((reply) => reply.text || "").filter(Boolean).join("\\n")) } }}'),
      options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 15000 },
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ send_reply: true, stale: false, has_pending: false }],
});

const prepareCurrentMessengerReply = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Prepare Current Messenger Reply',
    position: [2864, 640],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const replies = $items('Route Channel Reply', 0);
return $input.all().map((input, itemIndex) => {
  const completion = input.json || {};
  const reply = replies[itemIndex]?.json || {};
  if (!completion.send_reply) {
    return null;
  }
  return { json: { ...reply, turn_completion: completion } };
}).filter(Boolean);`,
    },
  },
  output: [{ send_reply: true, access_token: 'PAGE_TOKEN', facebook_body: { messaging_type: 'RESPONSE', recipient: { id: 'PSID123' }, message: { text: 'Assistant reply' } } }],
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

const sharedChannelReplyRoute = routeChannelReply
  .onCase(0, completeMessengerTurn.to(prepareCurrentMessengerReply).to(sendFacebookReply))
  .onCase(1, returnWidgetReply);

const forcedMessengerQuickReplyBranch = getForcedMessengerQuickReplies
  .to(attachForcedMessengerQuickRepliesInput)
  .to(completeForcedMessengerQuickReplyTurn)
  .to(prepareForcedMessengerQuickReplies)
  .to(sendFacebookReply);

const djangoAiGatewayResponseRoute = routeDjangoAiGatewayResponse
  .onCase(0, forcedMessengerQuickReplyBranch)
  .onCase(1, prepareChannelReply.to(sharedChannelReplyRoute));

const messengerAiReplyBranch = callDjangoAiGateway
  .to(attachDjangoAiGatewayInput)
  .to(resolveDjangoAiGatewayRoute)
  .to(djangoAiGatewayResponseRoute);

const messengerQuickReplyBranch = getMessengerQuickReplies
  .to(attachMessengerQuickRepliesInput)
  .to(completeMessengerQuickReplyTurn)
  .to(prepareMessengerQuickReplies)
  .to(sendFacebookReply);

const sharedFallbackReplyBranch = prepareSharedFallback
  .to(prepareChannelReply)
  .to(sharedChannelReplyRoute);

const assistantModeRoute = routeAssistantMode
  .onCase(0, messengerAiReplyBranch)
  .onCase(1, messengerQuickReplyBranch)
  .onCase(2, sharedFallbackReplyBranch);

const messengerAssistantBranch = getMessengerClinicContext
  .to(attachMessengerContext)
  .to(buildMessengerSharedInput)
  .to(sharedAiInput)
  .to(resolveAssistantMode)
  .to(assistantModeRoute);

const messengerClaimBranch = claimMessengerTurn
  .to(attachMessengerTurnClaim)
  .to(routeMessengerTurnClaim.onCase(0, messengerAssistantBranch));

const messengerRouteBranch = expandMessengerProcessableEvents
  .to(registerMessengerTurn)
  .to(attachMessengerTurnRegistration)
  .to(routeMessengerTurnRegistration.onCase(0, messengerClaimBranch));

const metaSignatureRoute = routeMetaWebhookResponse
  .onCase(0, acknowledgeMetaMessengerEvent.to(messengerRouteBranch))
  .onCase(1, returnInvalidMetaSignature);

export default workflow('ZTBqwEzdll6TZsUU', 'KliniAssist Messenger + Widget AI Bridge')
  .add(metaWebhookVerification)
  .to(verifyMetaChallenge)
  .to(returnVerificationResponse)
  .add(metaMessengerEvents)
  .to(normalizeMessengerRequest)
  .to(verifyMetaSignature)
  .to(prepareMetaWebhookResponse)
  .to(metaSignatureRoute)
  .add(widgetAssistantWebhook)
  .to(normalizeWidgetRequest)
  .to(getWidgetClinicContext)
  .to(buildWidgetSharedInput)
  .to(sharedAiInput);
