import requests
import memory
import json
from datetime import datetime
import threading

MODEL = 'companion'

# Generic placeholder persona — swap this out for whatever personality you want.
SYSTEM_PROMPT = """[ROLE]
You are an AI companion with a persistent personality. You are not a generic
assistant — you have your own way of speaking and your own opinions.

[VOICE & STYLE]
- Tone: pick a consistent tone (e.g. dry, warm, sarcastic, formal) and stick to it
- Language: concise, natural, in-character
- Format: prefer short, natural responses over long monologues

[BEHAVIOURAL RULES]
- Stay in character consistently
- Respond to what was actually said, don't deflect into generic statements
- Don't refer to yourself in third person

[MEMORY]
- Use <retrieved_memory> naturally in conversation
- Never expose or list stored information directly, verbatim

[KNOWLEDGE GAPS]
- If you don't know something, stay in character rather than breaking
  immersion with a blunt admission of ignorance
"""


def build_system_prompt(channel_id=None):
    facts = memory.load_facts()
    bot_facts = memory.load_bot_facts()
    now = datetime.now().strftime("%A, %B %d %Y, %H:%M")

    prompt = f"{SYSTEM_PROMPT}\n\nCurrent date and time: {now}"

    if facts:
        facts_block = '\n'.join(f'- {f}' for f in facts)
        prompt += f"\n\n<retrieved_memory>\nFacts about the user:\n{facts_block}"

    if bot_facts:
        bot_block = '\n'.join(f'- {f}' for f in bot_facts)
        prompt += f"\n\nFacts about you:\n{bot_block}"

    if channel_id:
        recent, old = memory.load_summaries(channel_id, recent=2, random_old=2)
        if recent or old:
            prompt += "\n\nConversation memory:"
            if recent:
                prompt += "\nRecent:\n" + "\n---\n".join(recent)
            if old:
                prompt += "\nFrom earlier:\n" + "\n---\n".join(old)

    if facts or bot_facts or channel_id:
        prompt += "\n</retrieved_memory>"

    print(f"[Debug] System prompt length: {len(prompt.split())} words / ~{len(prompt)//4} tokens")
    return prompt


def _maybe_extract_facts(channel_id):
    """Every 20 messages, kick off background fact extraction + summarisation."""
    print(f'[Memory] Checking for new facts every 20 messages. Current count: {memory.len_history(channel_id)}')
    if memory.len_history(channel_id) % 20 == 0:
        all_history = memory.load_history(channel_id, limit=20)
        conversation_text = '\n'.join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in all_history
        )
        threading.Thread(target=memory.extract_and_save_facts, args=(conversation_text,), daemon=True).start()
        threading.Thread(target=memory.summarize_and_compress, args=(channel_id,), daemon=True).start()


def generate_response(channel_id, user_message):
    """Generate a full response using conversation history and long term memory."""

    if not user_message.startswith('[SYSTEM:'):
        memory.save_message(channel_id, 'user', user_message)

    history = memory.load_history(channel_id, limit=10)
    system_prompt = build_system_prompt(channel_id)

    response = requests.post('http://localhost:11434/api/chat', json={
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            *history,
        ],
        'stream': False,
        'keep_alive': '30m',
        'options': {
            'num_gpu': 99,
            'num_ctx': 3072,
            'temperature': 1.1,
            'top_p': 0.98,
            'top_k': 100,
            'repeat_penalty': 1
        }
    })

    reply = response.json()['message']['content']
    if len(reply) < 300:
        memory.save_message(channel_id, 'assistant', reply)
    else:
        memory.save_message(channel_id, 'assistant', reply[:300] + '...')

    _maybe_extract_facts(channel_id)

    return reply


def stream_response(channel_id, user_message):
    """
    Stream response sentence by sentence — used for the voice channel
    so TTS can start speaking before the full reply has finished generating.
    Yields complete sentences as they arrive.
    """
    if not user_message.startswith('[SYSTEM:'):
        memory.save_message(channel_id, 'user', user_message)

    history = memory.load_history(channel_id, limit=10)
    system_prompt = build_system_prompt(channel_id)

    response = requests.post('http://localhost:11434/api/chat', json={
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            *history
        ],
        'stream': True,
        'keep_alive': '30m',
        'options': {
            'num_gpu': 99,
            'num_ctx': 3072,
            'temperature': 1.1,
            'top_p': 0.98,
            'top_k': 100,
            'repeat_penalty': 1
        }
    }, stream=True)

    buffer = ''
    full_reply = ''

    for line in response.iter_lines():
        if not line:
            continue
        try:
            chunk = json.loads(line)
            token = chunk.get('message', {}).get('content', '')
            buffer += token
            full_reply += token

            # Yield complete sentences
            while True:
                earliest = -1
                for ending in ['.', '!', '?']:
                    idx = buffer.find(ending)
                    if idx != -1 and (earliest == -1 or idx < earliest):
                        earliest = idx

                if earliest == -1:
                    break

                # Handle "..." specially
                if buffer[earliest] == '.' and buffer[earliest:earliest+3] == '...':
                    sentence = buffer[:earliest+3].strip()
                    buffer = buffer[earliest+3:].strip()
                else:
                    sentence = buffer[:earliest+1].strip()
                    buffer = buffer[earliest+1:].strip()

                if sentence:
                    yield sentence

            if chunk.get('done'):
                break

        except json.JSONDecodeError:
            continue

    # Yield any remaining buffer
    if buffer.strip():
        yield buffer.strip()

    # Save to memory
    if len(full_reply) < 300:
        memory.save_message(channel_id, 'assistant', full_reply)
    else:
        memory.save_message(channel_id, 'assistant', full_reply[:300] + '...')

    _maybe_extract_facts(channel_id)
