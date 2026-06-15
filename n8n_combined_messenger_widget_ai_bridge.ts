import {
  workflow,
  node,
  trigger,
  switchCase,
  newCredential,
  expr,
} from '@n8n/workflow-sdk';

const N8N_WEBHOOK_CREDENTIAL_ID = 'PJHqVMwE3qU58s9E';
const MESSENGER_FALLBACK = 'Thanks for your message. Please contact the clinic directly for help.';
const WIDGET_FALLBACK = 'Sorry, the assistant is unavailable right now. You can still book an appointment using the booking form.';
const DJANGO_MESSENGER_WEBHOOK_URL_EXPR = expr('{{ (() => { const callbackUrls = $json.callback_urls || {}; const value = String(callbackUrls["messenger_webhook_url"] || "").trim(); if (!value) { throw new Error("callback_urls.messenger_webhook_url is required"); } if (!value.startsWith("https://")) { throw new Error("callback_urls.messenger_webhook_url must use https"); } return value; })() }}');
const DJANGO_META_SIGNATURE_VERIFY_URL_EXPR = expr('{{ (() => { const callbackUrls = $json.callback_urls || {}; const value = String(callbackUrls["meta_signature_verify_url"] || "").trim(); if (!value) { throw new Error("callback_urls.meta_signature_verify_url is required"); } if (!value.startsWith("https://")) { throw new Error("callback_urls.meta_signature_verify_url must use https"); } return value; })() }}');
const DJANGO_MESSENGER_AI_CONTEXT_URL_EXPR = expr('{{ (() => { const callbackUrls = $json.callback_urls || {}; const value = String(callbackUrls["messenger_ai_context_url"] || "").trim(); if (!value) { throw new Error("callback_urls.messenger_ai_context_url is required"); } if (!value.startsWith("https://")) { throw new Error("callback_urls.messenger_ai_context_url must use https"); } return value; })() }}');
const DJANGO_AI_GATEWAY_REPLY_URL_EXPR = expr('{{ (() => { const callbackUrls = $json.callback_urls || {}; const value = String(callbackUrls["ai_gateway_reply_url"] || "").trim(); if (!value) { throw new Error("callback_urls.ai_gateway_reply_url is required"); } if (!value.startsWith("https://")) { throw new Error("callback_urls.ai_gateway_reply_url must use https"); } return value; })() }}');
const DJANGO_WIDGET_AI_CONTEXT_URL_EXPR = expr('{{ (() => { const callbackUrls = $json.callback_urls || {}; const value = String(callbackUrls["widget_ai_context_url"] || "").trim(); if (!value) { throw new Error("callback_urls.widget_ai_context_url is required"); } if (!value.startsWith("https://")) { throw new Error("callback_urls.widget_ai_context_url must use https"); } return value; })() }}');
const DJANGO_MESSENGER_AI_TURN_REGISTER_URL_EXPR = expr('{{ (() => { const callbackUrls = $json.callback_urls || {}; const value = String(callbackUrls["messenger_ai_turn_register_url"] || "").trim(); if (!value) { throw new Error("callback_urls.messenger_ai_turn_register_url is required"); } if (!value.startsWith("https://")) { throw new Error("callback_urls.messenger_ai_turn_register_url must use https"); } return value; })() }}');
const DJANGO_MESSENGER_AI_TURN_CLAIM_URL_EXPR = expr('{{ (() => { const callbackUrls = $json.callback_urls || {}; const value = String(callbackUrls["messenger_ai_turn_claim_url"] || "").trim(); if (!value) { throw new Error("callback_urls.messenger_ai_turn_claim_url is required"); } if (!value.startsWith("https://")) { throw new Error("callback_urls.messenger_ai_turn_claim_url must use https"); } return value; })() }}');
const DJANGO_MESSENGER_AI_TURN_SEND_REPLY_URL_EXPR = expr('{{ (() => { const callbackUrls = $json.callback_urls || {}; const value = String(callbackUrls["messenger_ai_turn_send_reply_url"] || "").trim(); if (!value) { throw new Error("callback_urls.messenger_ai_turn_send_reply_url is required"); } if (!value.startsWith("https://")) { throw new Error("callback_urls.messenger_ai_turn_send_reply_url must use https"); } return value; })() }}');
const DJANGO_MESSENGER_N8N_WEBHOOK_URL_EXPR = expr('{{ (() => { const callbackUrls = $json.callback_urls || {}; const value = String(callbackUrls["messenger_n8n_webhook_url"] || "").trim(); if (!value) { throw new Error("callback_urls.messenger_n8n_webhook_url is required"); } if (!value.startsWith("https://")) { throw new Error("callback_urls.messenger_n8n_webhook_url must use https"); } return value; })() }}');
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
  output: [{ query: { 'hub.mode': 'subscribe', 'hub.verify_token': 'configured-token', 'hub.challenge': '123456789' }, callback_urls: { messenger_webhook_url: 'https://callback.example.test/messenger/webhook/', meta_signature_verify_url: 'https://callback.example.test/messenger/meta/verify-signature/', messenger_ai_context_url: 'https://callback.example.test/messenger/ai/context/', ai_gateway_reply_url: 'https://callback.example.test/messenger/ai/gateway/reply/', messenger_ai_turn_register_url: 'https://callback.example.test/messenger/ai/turn/register/', messenger_ai_turn_claim_url: 'https://callback.example.test/messenger/ai/turn/claim/', messenger_ai_turn_send_reply_url: 'https://callback.example.test/messenger/ai/turn/send-reply/', messenger_n8n_webhook_url: 'https://callback.example.test/messenger/n8n-webhook/' } }],
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
      authentication: 'headerAuth',
      responseMode: 'responseNode',
      options: { rawBody: true },
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
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
if (typeof body.raw_body === 'string' && body.raw_body.trim()) {
  rawBody = body.raw_body;
}
const callbackUrls = body.callback_urls && typeof body.callback_urls === 'object' ? body.callback_urls : {};
const requiredCallbackUrls = [
  'meta_signature_verify_url',
  'messenger_ai_turn_register_url',
  'messenger_ai_turn_claim_url',
  'messenger_ai_context_url',
  'ai_gateway_reply_url',
  'messenger_n8n_webhook_url',
  'messenger_ai_turn_send_reply_url',
];
for (const key of requiredCallbackUrls) {
  const value = String(callbackUrls[key] || '').trim();
  if (!value) {
    throw new Error('callback_urls.' + key + ' is required');
  }
  if (!value.startsWith('https://')) {
    throw new Error('callback_urls.' + key + ' must use https');
  }
}
const MESSENGER_LIKE_STICKER_IDS = new Set(['369239263222822']);
const MESSENGER_LIKE_GREETING_TEXT = 'Hi';
function messengerLikeGreetingText(message) {
  const attachments = Array.isArray(message?.attachments) ? message.attachments : [];
  for (const attachment of attachments) {
    const payload = attachment && typeof attachment === 'object' ? attachment.payload : {};
    const stickerId = String(payload?.sticker_id || '').trim();
    if (MESSENGER_LIKE_STICKER_IDS.has(stickerId)) {
      return MESSENGER_LIKE_GREETING_TEXT;
    }
  }
  return '';
}
if (body.channel === 'messenger' && Object.keys(callbackUrls).length) {
  const pageId = String(body.page_id || body.pageId || '').trim();
  const psid = String(body.psid || body.sender_id || '').trim();
  const message = String(body.message || body.text || '').trim();
  const postback = String(body.postback || '').trim();
  const messageId = String(body.message_id || body.messageId || '').trim();
  const signatureValue = String(body.signature || '').trim();
  return [{ json: {
    channel: 'messenger',
    message,
    postback,
    page_id: pageId,
    psid,
    message_id: messageId,
    clinic_slug: String(body.clinic_slug || body.clinicSlug || '').trim(),
    clinic_id: body.clinic_id || body.clinicId || '',
    session_id: '',
    session_key: 'messenger:' + (pageId || 'unknown-page') + ':' + (psid || 'unknown-psid'),
    output_mode: 'facebook',
    ignored_event: !pageId || !psid || (!message && !postback),
    raw_body: rawBody,
    signature: signatureValue,
    callback_urls: callbackUrls
  } }];
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
    const rawMessage = String(messaging.message?.text || '').trim();
    const message = rawMessage || messengerLikeGreetingText(messaging.message || {});
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
      signature,
      callback_urls: callbackUrls
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
    signature,
    callback_urls: callbackUrls
  } });
}
return items;`,
    },
  },
  output: [{ channel: 'messenger', message: 'Can I book cleaning tomorrow?', postback: '', page_id: 'PAGE123', psid: 'PSID123', message_id: 'mid.123', clinic_slug: '', session_id: '', session_key: 'messenger:PAGE123:PSID123', output_mode: 'facebook', ignored_event: false, raw_body: '{"entry":[{"id":"PAGE123"}]}', signature: 'sha256=abc123', callback_urls: { messenger_webhook_url: 'https://callback.example.test/messenger/webhook/', meta_signature_verify_url: 'https://callback.example.test/messenger/meta/verify-signature/', messenger_ai_context_url: 'https://callback.example.test/messenger/ai/context/', ai_gateway_reply_url: 'https://callback.example.test/messenger/ai/gateway/reply/', messenger_ai_turn_register_url: 'https://callback.example.test/messenger/ai/turn/register/', messenger_ai_turn_claim_url: 'https://callback.example.test/messenger/ai/turn/claim/', messenger_ai_turn_send_reply_url: 'https://callback.example.test/messenger/ai/turn/send-reply/', messenger_n8n_webhook_url: 'https://callback.example.test/messenger/n8n-webhook/' } }],
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
  output: [{ response_route: 'acknowledge', processable_events: [{ channel: 'messenger', page_id: 'PAGE123', psid: 'PSID123', message_id: 'mid.123', message: 'Hello', postback: '', raw_body: '{}', signature: 'sha256=abc123', verified: true, duplicate: false, ignored_event: false, callback_urls: { messenger_webhook_url: 'https://callback.example.test/messenger/webhook/', meta_signature_verify_url: 'https://callback.example.test/messenger/meta/verify-signature/', messenger_ai_context_url: 'https://callback.example.test/messenger/ai/context/', ai_gateway_reply_url: 'https://callback.example.test/messenger/ai/gateway/reply/', messenger_ai_turn_register_url: 'https://callback.example.test/messenger/ai/turn/register/', messenger_ai_turn_claim_url: 'https://callback.example.test/messenger/ai/turn/claim/', messenger_ai_turn_send_reply_url: 'https://callback.example.test/messenger/ai/turn/send-reply/', messenger_n8n_webhook_url: 'https://callback.example.test/messenger/n8n-webhook/' } }] }],
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
  output: [{ channel: 'messenger', page_id: 'PAGE123', psid: 'PSID123', message_id: 'mid.123', message: 'Hello', postback: '', raw_body: '{}', signature: 'sha256=abc123', verified: true, duplicate: false, ignored_event: false, callback_urls: { messenger_webhook_url: 'https://callback.example.test/messenger/webhook/', meta_signature_verify_url: 'https://callback.example.test/messenger/meta/verify-signature/', messenger_ai_context_url: 'https://callback.example.test/messenger/ai/context/', ai_gateway_reply_url: 'https://callback.example.test/messenger/ai/gateway/reply/', messenger_ai_turn_register_url: 'https://callback.example.test/messenger/ai/turn/register/', messenger_ai_turn_claim_url: 'https://callback.example.test/messenger/ai/turn/claim/', messenger_ai_turn_send_reply_url: 'https://callback.example.test/messenger/ai/turn/send-reply/', messenger_n8n_webhook_url: 'https://callback.example.test/messenger/n8n-webhook/' } }],
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
      jsonBody: expr('{{ { page_id: $json.page_id, psid: $json.psid, message_id: $json.message_id, message: $json.message, postback: $json.postback || "", raw_body: $json.raw_body, signature: $json.signature } }}'),
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
  output: [{ body: { channel: 'widget', clinic_id: 1, clinic_slug: 'demo-clinic', message: 'Can I book tomorrow?', history: [], session_id: 'SESSION123', callback_urls: { widget_ai_context_url: 'https://callback.example.test/messenger/ai/widget/context/', ai_gateway_reply_url: 'https://callback.example.test/messenger/ai/gateway/reply/', messenger_n8n_webhook_url: 'https://callback.example.test/messenger/n8n-webhook/' } } }],
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
const callbackUrls = body.callback_urls && typeof body.callback_urls === 'object' ? body.callback_urls : {};
const requiredCallbackUrls = [
  'widget_ai_context_url',
  'ai_gateway_reply_url',
  'messenger_n8n_webhook_url',
];
for (const key of requiredCallbackUrls) {
  const value = String(callbackUrls[key] || '').trim();
  if (!value) {
    throw new Error('callback_urls.' + key + ' is required');
  }
  if (!value.startsWith('https://')) {
    throw new Error('callback_urls.' + key + ' must use https');
  }
}
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
  output_mode: 'widget_json',
  callback_urls: callbackUrls,
} }];`,
    },
  },
  output: [{ channel: 'widget', message: 'Can I book tomorrow?', page_id: '', psid: '', clinic_slug: 'demo-clinic', clinic_id: 1, history: [], session_id: 'SESSION123', session_key: 'widget:demo-clinic:SESSION123', output_mode: 'widget_json', callback_urls: { widget_ai_context_url: 'https://callback.example.test/messenger/ai/widget/context/', ai_gateway_reply_url: 'https://callback.example.test/messenger/ai/gateway/reply/', messenger_n8n_webhook_url: 'https://callback.example.test/messenger/n8n-webhook/' } }],
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
      jsonBody: expr('{{ { page_id: $json.page_id, psid: $json.psid, turn_token: $json.turn_token || "", input_sequence: $json.input_sequence || 0 } }}'),
      options: { response: { response: { neverError: true, responseFormat: 'json' } }, timeout: 15000 },
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ found: true, page_id: 'PAGE123', clinic: { id: 1, name: 'Demo Clinic', timezone: 'Asia/Manila' }, current_time: { timezone: 'Asia/Manila', now: '2026-06-01T09:00:00+08:00', today: '2026-06-01' }, ai: { is_ai_enabled: true, instructions: 'Be helpful.', fallback_message: MESSENGER_FALLBACK }, services: [], faqs: [] }],
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
    context
  } };
});`,
    },
  },
  output: [{ channel: 'messenger', page_id: 'PAGE123', psid: 'PSID123', message: 'New Messenger messages in order:\n- June 15\n- Cleaning', raw_message: 'Cleaning', raw_postback: '', turn_token: 'turn-token', input_sequence: 2, context: { found: true, ai: { is_ai_enabled: true } } }],
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
      jsCode: `function sanitizeServicePricing(value) {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeServicePricing(item));
  }
  if (value && typeof value === 'object') {
    const clone = { ...value };
    delete clone.price;
    delete clone.display_price;
    for (const key of Object.keys(clone)) {
      clone[key] = sanitizeServicePricing(clone[key]);
    }
    return clone;
  }
  return value;
}

return $input.all().map((inputItem) => {
  const input = inputItem.json || {};
  const rawContext = input.context || {};
  const sanitizedContext = sanitizeServicePricing(rawContext);
  const claim = input.claim || {};
  const aiVersion = rawContext.ai?.settings_updated_at || 'unversioned';
  return { json: { ...input, message: claim.message || input.message || '', turn_token: claim.turn_token || input.turn_token || '', input_sequence: claim.input_sequence || input.input_sequence || 0, turn_messages: claim.messages || input.turn_messages || [], history: claim.history || input.history || [], session_key: input.session_key + ':ai-settings:' + aiVersion + ':turn:' + (claim.turn_token || input.turn_token || 'no-turn'), context: sanitizedContext, fallback_message: rawContext.ai?.fallback_message || '${MESSENGER_FALLBACK}' } };
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
      jsCode: `function sanitizeServicePricing(value) {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeServicePricing(item));
  }
  if (value && typeof value === 'object') {
    const clone = { ...value };
    delete clone.price;
    delete clone.display_price;
    for (const key of Object.keys(clone)) {
      clone[key] = sanitizeServicePricing(clone[key]);
    }
    return clone;
  }
  return value;
}

const context = $input.first().json || {};
const source = $items('Normalize Widget Request')[0].json || {};
const sanitizedContext = sanitizeServicePricing(context);
const aiVersion = context.ai?.settings_updated_at || 'unversioned';
return [{ json: { ...source, session_key: source.session_key + ':ai-settings:' + aiVersion, context: sanitizedContext, fallback_message: context.ai?.fallback_message || '${WIDGET_FALLBACK}' } }];`,
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
  output: [{ replies: [{ type: 'quick_replies', text: 'Choose an option:', options: [{ title: 'Book an appointment', payload: 'start_booking' }] }] }],
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
    replies: Array.isArray(response.replies) ? response.replies : []
  } };
});`,
    },
  },
  output: [{ channel: 'messenger', page_id: 'PAGE123', psid: 'PSID123', turn_token: 'turn-token', input_sequence: 2, replies: [{ type: 'quick_replies', text: 'Choose an option:', options: [{ title: 'Book an appointment', payload: 'start_booking' }] }] }],
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
for (const inputItem of $input.all()) {
  const input = inputItem.json || {};
  const actions = Array.isArray(input.replies) ? input.replies : [];
  const psid = input.psid || '';
  if (!psid) { continue; }
  const facebookBodies = [];
  const replyTexts = [];
  const appendBody = (facebookBody, replyText) => {
    facebookBodies.push(facebookBody);
    replyTexts.push(replyText);
  };
  for (const action of actions) {
    if (action.type === 'text') {
      const text = String(action.text || '');
      appendBody({ messaging_type: 'RESPONSE', recipient: { id: psid }, message: { text } }, text);
    }
    if (action.type === 'quick_replies') {
      const quickReplies = (action.options || []).slice(0, 13).map((option) => ({ content_type: 'text', title: String(option.title || '').slice(0, 20), payload: String(option.payload || '') }));
      const message = { text: String(action.text || '') };
      if (quickReplies.length) { message.quick_replies = quickReplies; }
      appendBody({ messaging_type: 'RESPONSE', recipient: { id: psid }, message }, message.text);
    }
  }
  if (!actions.length) {
    const fallback = input.fallback_message || '${MESSENGER_FALLBACK}';
    appendBody({ messaging_type: 'RESPONSE', recipient: { id: psid }, message: { text: fallback } }, fallback);
  }
  if (facebookBodies.length) {
    items.push({ json: { ...input, facebook_bodies: facebookBodies, reply_text: replyTexts.filter(Boolean).join('\n'), page_id: input.page_id || '', psid, turn_token: input.turn_token || '', input_sequence: input.input_sequence || 0 } });
  }
}
return items;`,
    },
  },
  output: [{ page_id: 'PAGE123', psid: 'PSID123', turn_token: 'turn-token', input_sequence: 2, reply_text: 'Choose an option:', facebook_bodies: [{ messaging_type: 'RESPONSE', recipient: { id: 'PSID123' }, message: { text: 'Choose an option:', quick_replies: [{ content_type: 'text', title: 'Book an appointment', payload: 'start_booking' }] } }], callback_urls: { messenger_webhook_url: 'https://callback.example.test/messenger/webhook/', meta_signature_verify_url: 'https://callback.example.test/messenger/meta/verify-signature/', messenger_ai_context_url: 'https://callback.example.test/messenger/ai/context/', ai_gateway_reply_url: 'https://callback.example.test/messenger/ai/gateway/reply/', messenger_ai_turn_register_url: 'https://callback.example.test/messenger/ai/turn/register/', messenger_ai_turn_claim_url: 'https://callback.example.test/messenger/ai/turn/claim/', messenger_ai_turn_send_reply_url: 'https://callback.example.test/messenger/ai/turn/send-reply/', messenger_n8n_webhook_url: 'https://callback.example.test/messenger/n8n-webhook/' } }],
});

const callDjangoAiGateway = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Call Django AI Gateway',
    position: [1744, 720],
    onError: 'continueErrorOutput',
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

const handleDjangoAiGatewayError = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Handle Django AI Gateway Error',
    position: [1968, 880],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `// Sync marker for Django AI gateway route: /messenger/ai/gateway/reply/
const sourceItems = $items('Route Assistant Mode', 0);
return $input.all().map((inputItem, itemIndex) => {
  const source = sourceItems[itemIndex]?.json || {};
  const channel = source.channel || 'widget';
  const fallback = source.fallback_message || (channel === 'messenger' ? '${MESSENGER_FALLBACK}' : '${WIDGET_FALLBACK}');
  return { json: { ...source, gateway_response: { reply: fallback, fallback: true, error: 'ai_gateway_transport_error' }, reply: fallback, fallback: true, error: 'ai_gateway_transport_error' } };
});`,
    },
  },
  output: [{ channel: 'messenger', page_id: 'PAGE123', psid: 'PSID123', turn_token: 'turn-token', input_sequence: 2, reply: MESSENGER_FALLBACK, fallback: true, error: 'ai_gateway_transport_error' }],
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
  output: [{ channel: 'messenger', page_id: 'PAGE123', psid: 'PSID123', reply: 'Assistant reply', fallback: false, error: '' }],
});

const resolveDjangoAiGatewayRoute = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Resolve Django AI Gateway Route',
    position: [2080, 720],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `const providerFallbackErrors = new Set(['ai_provider_unconfigured', 'ai_provider_error', 'empty_provider_reply', 'tool_loop_exceeded', 'ai_gateway_transport_error']);
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
  output: [{ replies: [{ type: 'quick_replies', text: 'Choose an option:', options: [{ title: 'Book an appointment', payload: 'start_booking' }] }] }],
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
    replies: Array.isArray(response.replies) ? response.replies : []
  } };
});`,
    },
  },
  output: [{ channel: 'messenger', page_id: 'PAGE123', psid: 'PSID123', turn_token: 'turn-token', input_sequence: 2, replies: [{ type: 'quick_replies', text: 'Choose an option:', options: [{ title: 'Book an appointment', payload: 'start_booking' }] }] }],
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
for (const inputItem of $input.all()) {
  const input = inputItem.json || {};
  const actions = Array.isArray(input.replies) ? input.replies : [];
  const psid = input.psid || '';
  if (!psid) { continue; }
  const facebookBodies = [];
  const replyTexts = [];
  const appendBody = (facebookBody, replyText) => {
    facebookBodies.push(facebookBody);
    replyTexts.push(replyText);
  };
  for (const action of actions) {
    if (action.type === 'text') {
      const text = String(action.text || '');
      appendBody({ messaging_type: 'RESPONSE', recipient: { id: psid }, message: { text } }, text);
    }
    if (action.type === 'quick_replies') {
      const quickReplies = (action.options || []).slice(0, 13).map((option) => ({ content_type: 'text', title: String(option.title || '').slice(0, 20), payload: String(option.payload || '') }));
      const message = { text: String(action.text || '') };
      if (quickReplies.length) { message.quick_replies = quickReplies; }
      appendBody({ messaging_type: 'RESPONSE', recipient: { id: psid }, message }, message.text);
    }
  }
  if (!actions.length) {
    const fallback = input.fallback_message || '${MESSENGER_FALLBACK}';
    appendBody({ messaging_type: 'RESPONSE', recipient: { id: psid }, message: { text: fallback } }, fallback);
  }
  if (facebookBodies.length) {
    items.push({ json: { ...input, facebook_bodies: facebookBodies, reply_text: replyTexts.filter(Boolean).join('\n'), page_id: input.page_id || '', psid, turn_token: input.turn_token || '', input_sequence: input.input_sequence || 0 } });
  }
}
return items;`,
    },
  },
  output: [{ page_id: 'PAGE123', psid: 'PSID123', turn_token: 'turn-token', input_sequence: 2, reply_text: 'Choose an option:', facebook_bodies: [{ messaging_type: 'RESPONSE', recipient: { id: 'PSID123' }, message: { text: 'Choose an option:', quick_replies: [{ content_type: 'text', title: 'Book an appointment', payload: 'start_booking' }] } }], callback_urls: { messenger_webhook_url: 'https://callback.example.test/messenger/webhook/', meta_signature_verify_url: 'https://callback.example.test/messenger/meta/verify-signature/', messenger_ai_context_url: 'https://callback.example.test/messenger/ai/context/', ai_gateway_reply_url: 'https://callback.example.test/messenger/ai/gateway/reply/', messenger_ai_turn_register_url: 'https://callback.example.test/messenger/ai/turn/register/', messenger_ai_turn_claim_url: 'https://callback.example.test/messenger/ai/turn/claim/', messenger_ai_turn_send_reply_url: 'https://callback.example.test/messenger/ai/turn/send-reply/', messenger_n8n_webhook_url: 'https://callback.example.test/messenger/n8n-webhook/' } }],
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
  const failedVerificationContext = ['unable to verify', "couldn't verify", 'could not verify', "doesn't match", 'does not match', 'not match', 'booked under', 'belongs to', 'lookup failed', 'not found'].some((term) => text.includes(term));
  return appointmentContext && failedVerificationContext;
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
  text = channel === 'messenger'
    ? String(text || '').replace(/\\*\\*([^*\\n]+?)\\*\\*/g, '$1').replace(/\\*([^*\\n]+?)\\*/g, '$1')
    : text;
  const maxLength = channel === 'messenger' ? 1900 : 1800;
  if (text.length > maxLength) {
    text = text.slice(0, maxLength);
  }
  return { json: {
    ...shared,
    reply_text: text,
    facebook_body: { messaging_type: 'RESPONSE', recipient: { id: shared.psid || '' }, message: { text } },
    widget_body: { reply: text }
  } };
});`,
    },
  },
  output: [{ channel: 'widget', reply_text: 'Assistant reply', facebook_body: { messaging_type: 'RESPONSE', recipient: { id: '' }, message: { text: 'Assistant reply' } }, widget_body: { reply: 'Assistant reply' } }],
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

const prepareCurrentMessengerReply = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Prepare Current Messenger Reply',
    position: [2864, 640],
    parameters: {
      mode: 'runOnceForAllItems',
      jsCode: `return $input.all().map((input) => ({ json: input.json || {} }));`,
    },
  },
  output: [{ send_reply: true, page_id: 'PAGE123', psid: 'PSID123', turn_token: 'turn-token', input_sequence: 2, facebook_body: { messaging_type: 'RESPONSE', recipient: { id: 'PSID123' }, message: { text: 'Assistant reply' } }, callback_urls: { messenger_webhook_url: 'https://callback.example.test/messenger/webhook/', meta_signature_verify_url: 'https://callback.example.test/messenger/meta/verify-signature/', messenger_ai_context_url: 'https://callback.example.test/messenger/ai/context/', ai_gateway_reply_url: 'https://callback.example.test/messenger/ai/gateway/reply/', messenger_ai_turn_register_url: 'https://callback.example.test/messenger/ai/turn/register/', messenger_ai_turn_claim_url: 'https://callback.example.test/messenger/ai/turn/claim/', messenger_ai_turn_send_reply_url: 'https://callback.example.test/messenger/ai/turn/send-reply/', messenger_n8n_webhook_url: 'https://callback.example.test/messenger/n8n-webhook/' } }],
});

const sendMessengerReplyViaDjango = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.4,
  config: {
    name: 'Send Messenger Reply via Django',
    position: [2864, 640],
    parameters: {
      method: 'POST',
      url: DJANGO_MESSENGER_AI_TURN_SEND_REPLY_URL_EXPR,
      authentication: 'genericCredentialType',
      genericAuthType: 'httpHeaderAuth',
      sendHeaders: true,
      headerParameters: { parameters: [{ name: 'Content-Type', value: 'application/json' }] },
      sendBody: true,
      specifyBody: 'json',
      jsonBody: expr('{{ { page_id: $json.page_id, psid: $json.psid, turn_token: $json.turn_token, input_sequence: $json.input_sequence || 0, reply_text: $json.reply_text || "", facebook_body: $json.facebook_body, facebook_bodies: $json.facebook_bodies || [] } }}'),
      options: { response: { response: { responseFormat: 'json' } }, timeout: 15000 },
    },
    credentials: { httpHeaderAuth: newCredential('KliniAssist N8N Webhook Secret', N8N_WEBHOOK_CREDENTIAL_ID) },
  },
  output: [{ send_reply: true, stale: false, has_pending: false, sent: true }],
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
  .onCase(0, prepareCurrentMessengerReply.to(sendMessengerReplyViaDjango))
  .onCase(1, returnWidgetReply);

const forcedMessengerQuickReplyBranch = getForcedMessengerQuickReplies
  .to(attachForcedMessengerQuickRepliesInput)
  .to(prepareForcedMessengerQuickReplies)
  .to(sendMessengerReplyViaDjango);

const djangoAiGatewayResponseRoute = routeDjangoAiGatewayResponse
  .onCase(0, forcedMessengerQuickReplyBranch)
  .onCase(1, prepareChannelReply.to(sharedChannelReplyRoute));

const messengerAiGatewayErrorBranch = handleDjangoAiGatewayError
  .to(resolveDjangoAiGatewayRoute)
  .to(djangoAiGatewayResponseRoute);

const messengerAiReplyBranch = callDjangoAiGateway
  .onError(messengerAiGatewayErrorBranch)
  .to(attachDjangoAiGatewayInput)
  .to(resolveDjangoAiGatewayRoute)
  .to(djangoAiGatewayResponseRoute);

const messengerQuickReplyBranch = getMessengerQuickReplies
  .to(attachMessengerQuickRepliesInput)
  .to(prepareMessengerQuickReplies)
  .to(sendMessengerReplyViaDjango);

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
