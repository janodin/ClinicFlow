import { workflow, node, trigger, expr } from '@n8n/workflow-sdk';

const facebookTrigger = trigger({
  type: 'n8n-nodes-base.facebookMessengerTrigger',
  version: 1,
  config: {
    name: 'Facebook Messenger Trigger',
    parameters: {
      updates: ['messages'],
      appId: '',
      appSecret: '',
      pageToken: '',
      pageIds: ''
    }
  }
});

const formatPayload = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Format Django Payload',
    parameters: {
      jsCode: `
return $input.all().map((input) => {
  const msg = input.json || {};
  const senderId = msg.sender?.id || msg.psid;
  const pageId = msg.recipient?.id || msg.page_id;
  const text = msg.message?.text || '';
  const postback = msg.postback?.payload || msg.message?.quick_reply?.payload || '';

  return {
    json: {
      page_id: pageId,
      psid: senderId,
      text: text,
      postback: postback
    }
  };
});
      `
    }
  }
});

const djangoWebhook = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: 'Django Webhook',
    parameters: {
      method: 'POST',
      url: 'https://clinic.example.com/messenger/n8n-webhook/',
      sendBody: true,
      bodyParameters: {
        parameters: [
          { name: 'page_id', value: expr('{{ $json.page_id }}') },
          { name: 'psid', value: expr('{{ $json.psid }}') },
          { name: 'text', value: expr('{{ $json.text }}') },
          { name: 'postback', value: expr('{{ $json.postback }}') }
        ]
      },
      headerParameters: {
        parameters: [
          { name: 'X-N8N-Webhook-Secret', value: 'replace-with-shared-n8n-webhook-secret' },
          { name: 'Content-Type', value: 'application/json' }
        ]
      },
      options: {
        response: {
          response: {
            neverError: true
          }
        }
      }
    }
  }
});

const formatReply = node({
  type: 'n8n-nodes-base.code',
  version: 2,
  config: {
    name: 'Format Facebook Reply',
    parameters: {
      jsCode: `
const results = [];

for (const [itemIndex, input] of $input.all().entries()) {
  const djangoResponse = input.json || {};
  const replies = djangoResponse.replies || [];
  const pageToken = djangoResponse.page_token || '';
  const psid = djangoResponse.psid || '';
  if (!pageToken || !psid) { continue; }
  for (const reply of replies) {
    if (reply.type === 'text') {
      results.push({
        json: {
          messaging_type: 'RESPONSE',
          recipient: { id: psid },
          message: { text: reply.text },
          page_token: pageToken
        }
      });
    } else if (reply.type === 'quick_replies') {
      const quickReplies = (reply.options || []).slice(0, 13).map(opt => ({
        content_type: 'text',
        title: String(opt.title || '').slice(0, 20),
        payload: String(opt.payload || '')
      }));
      const message = { text: reply.text };
      if (quickReplies.length) {
        message.quick_replies = quickReplies;
      }
      results.push({
        json: {
          messaging_type: 'RESPONSE',
          recipient: { id: psid },
          message,
          page_token: pageToken
        }
      });
    }
  }
}

return results;
      `
    }
  }
});

const sendReply = node({
  type: 'n8n-nodes-base.httpRequest',
  version: 4.2,
  config: {
    name: 'Send Facebook Reply',
    parameters: {
      method: 'POST',
      url: 'https://graph.facebook.com/v18.0/me/messages',
      sendQuery: true,
      queryParameters: {
        parameters: [
          { name: 'access_token', value: expr('{{ $json.page_token }}') }
        ]
      },
      sendBody: true,
      bodyParameters: {
        parameters: [
          { name: 'messaging_type', value: expr('{{ $json.messaging_type }}') },
          { name: 'recipient', value: expr('{{ JSON.stringify($json.recipient) }}') },
          { name: 'message', value: expr('{{ JSON.stringify($json.message) }}') }
        ]
      }
    }
  }
});

export default workflow('clinic-messenger', 'Clinic Messenger - Booking Bot')
  .add(facebookTrigger)
  .to(formatPayload)
  .to(djangoWebhook)
  .to(formatReply)
  .to(sendReply);
