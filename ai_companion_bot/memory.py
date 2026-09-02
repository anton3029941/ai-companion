import sqlite3
import requests
from difflib import SequenceMatcher

DB_PATH = 'bot_memory.db'
MODEL = 'companion'

def init_db():
    """Initialize the database with required tables."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Conversation history table
    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT,
            role TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Long term facts about the user
    c.execute('''
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact TEXT UNIQUE,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Long term facts about the bot itself
    c.execute('''
        CREATE TABLE IF NOT EXISTS bot_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact TEXT UNIQUE,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT,
            summary TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

def save_message(channel_id, role, content):
    """Save a single message to history."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO history (channel_id, role, content) VALUES (?, ?, ?)',
              (str(channel_id), role, content))
    conn.commit()
    conn.close()

def load_history(channel_id, limit=10):
    """Load the last N messages from a channel."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT role, content FROM history
        WHERE channel_id = ?
        ORDER BY id DESC
        LIMIT ?
    ''', (str(channel_id), limit))
    rows = c.fetchall()
    conn.close()
    return [{'role': row[0], 'content': row[1]} for row in reversed(rows)]

def len_history(channel_id):
    """Return the total number of messages in a channel's history."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM history WHERE channel_id = ?', (str(channel_id),))
    count = c.fetchone()[0]
    conn.close()
    return count

def save_summary(channel_id, summary):
    """Save a new summary entry for a channel."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'INSERT INTO summaries (channel_id, summary) VALUES (?, ?)',
        (str(channel_id), summary)
    )
    conn.commit()
    conn.close()

def load_summaries(channel_id, recent=2, random_old=2):
    """Load 2 most recent + 2 random older summaries with timestamps."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get 2 most recent
    c.execute('''
        SELECT id, summary, timestamp FROM summaries
        WHERE channel_id = ?
        ORDER BY id DESC
        LIMIT ?
    ''', (str(channel_id), recent))
    recent_rows = c.fetchall()
    recent_ids = [r[0] for r in recent_rows]

    # Get random older ones excluding recent
    if recent_ids:
        placeholders = ','.join('?' * len(recent_ids))
        c.execute(f'''
            SELECT summary, timestamp FROM summaries
            WHERE channel_id = ? AND id NOT IN ({placeholders})
            ORDER BY RANDOM()
            LIMIT ?
        ''', (str(channel_id), *recent_ids, random_old))
        old_rows = c.fetchall()
    else:
        old_rows = []

    conn.close()

    def format_entry(summary, timestamp):
        try:
            from datetime import datetime
            dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            now = datetime.now()
            delta = now - dt

            if delta.days == 0:
                hours = delta.seconds // 3600
                if hours == 0:
                    age = "just now"
                elif hours == 1:
                    age = "1 hour ago"
                else:
                    age = f"{hours} hours ago"
            elif delta.days == 1:
                age = "yesterday"
            elif delta.days < 7:
                age = f"{delta.days} days ago"
            elif delta.days < 30:
                weeks = delta.days // 7
                age = f"{weeks} week{'s' if weeks > 1 else ''} ago"
            else:
                months = delta.days // 30
                age = f"{months} month{'s' if months > 1 else ''} ago"

            return f"[{age}]\n{summary}"
        except:
            return summary

    recent_summaries = [format_entry(r[1], r[2]) for r in recent_rows]
    old_summaries = [format_entry(r[0], r[1]) for r in old_rows]

    return recent_summaries, old_summaries

def delete_old_messages(channel_id, keep_last=10):
    """Delete all but the last N messages for a channel."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        DELETE FROM history
        WHERE channel_id = ? AND id NOT IN (
            SELECT id FROM history
            WHERE channel_id = ?
            ORDER BY id DESC
            LIMIT ?
        )
    ''', (str(channel_id), str(channel_id), keep_last))
    deleted = conn.total_changes
    conn.commit()
    conn.close()
    print(f"[Memory] Deleted {deleted} old messages, kept last {keep_last}.")

def summarize_and_compress(channel_id):
    """Summarize oldest 20 messages and delete exactly those 20, keeping 10 newest."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Only compress if we have more than 30 messages
    c.execute('SELECT COUNT(*) FROM history WHERE channel_id = ?', (str(channel_id),))
    total = c.fetchone()[0]

    if total < 30:
        print(f"[Memory] Not enough messages to compress ({total}/30).")
        conn.close()
        return

    # Get oldest 20 messages specifically
    c.execute('''
        SELECT id, role, content FROM history
        WHERE channel_id = ?
        ORDER BY id ASC
        LIMIT 20
    ''', (str(channel_id),))
    rows = c.fetchall()
    conn.close()

    # Build conversation text from those exact 20
    conversation_text = '\n'.join(
        f"{'User' if r[1] == 'user' else 'Assistant'}: {r[2]}"
        for r in rows
    )

    recent, old = load_summaries(channel_id, recent=1, random_old=0)
    existing_summary = recent[0] if recent else None
    existing_block = f"\nPrevious summary:\n{existing_summary}\n" if existing_summary else ""

    summary_prompt = f"""Summarize this conversation between the user and the assistant in 3-5 sentences.
Focus on: topics discussed, jokes made, things learned about each other, memorable moments.
Write it as a neutral third-person summary. Keep it under 150 words.
{existing_block}
New conversation:
{conversation_text}

Reply with ONLY the summary, no intro or explanation."""

    try:
        response = requests.post('http://localhost:11434/api/chat', json={
            'model': MODEL,
            'messages': [{'role': 'user', 'content': summary_prompt}],
            'stream': False,
            'options': {'num_gpu': 99, 'num_ctx': 3072, 'temperature': 0.3}
        })
        summary = response.json()['message']['content'].strip()
        save_summary(channel_id, summary)
        print(f"[Memory] Summary saved: {summary[:80]}...")

        # Delete exactly those 20 messages by ID
        ids = [r[0] for r in rows]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(f'''
            DELETE FROM history
            WHERE id IN ({",".join("?" * len(ids))})
        ''', ids)
        conn.commit()
        conn.close()
        print(f"[Memory] Deleted exactly 20 oldest messages.")

    except Exception as e:
        print(f'[Memory] Failed to summarize: {e}')

def is_duplicate(new_fact, existing_facts, threshold=0.7):
    """Check if a fact is too similar to existing ones."""
    for fact in existing_facts:
        ratio = SequenceMatcher(None, new_fact.lower(), fact.lower()).ratio()
        if ratio > threshold:
            return True
    return False

def summarise_facts(column):
    """Summarise a list of facts into a concise form."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    facts = load_facts() if column == 'facts' else load_bot_facts()
    length = c.execute(f'SELECT COUNT(*) FROM {column}').fetchone()[0]

    if length > 10:
        response = requests.post('http://localhost:11434/api/chat', json={
            'model': MODEL,
            'messages': [
                {'role': 'system', 'content': f'Summarise these {length} facts into a concise list of 5 the most important ones in format "-[fact]\n-[fact]" and so on:\n\n' + '\n'.join(f'- {f}' for f in facts)}
            ],
            'stream': False,
            'options': {
                'num_gpu': 99,
                'num_ctx': 3072,
            }
        })
        summary = response.json()['message']['content'].strip()

        c.execute(f'DELETE FROM {column}')
        for line in summary.split('\n'):
            line = line.strip()
            if line.startswith('-'):
                fact = line[1:].strip()
                try:
                    c.execute(f'INSERT INTO {column} (fact) VALUES (?)', (fact,))
                except sqlite3.IntegrityError:
                    pass

def save_fact(fact):
    """Save a user fact, ignoring duplicates and near-duplicates."""
    existing = load_facts()
    if is_duplicate(fact, existing):
        print(f"[Memory] Skipping duplicate user fact: {fact}")
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    length = c.execute('SELECT COUNT(*) FROM facts').fetchone()[0]
    if length >= 10:
        summarise_facts('facts')
    try:
        c.execute('INSERT INTO facts (fact) VALUES (?)', (fact,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def load_facts():
    """Load all long term facts about the user."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT fact FROM facts ORDER BY id')
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def save_bot_fact(fact):
    """Save a fact about the bot itself, ignoring duplicates."""
    existing = load_bot_facts()
    if is_duplicate(fact, existing):
        print(f"[Memory] Skipping duplicate bot fact: {fact}")
        return
    if len(existing) >= 10:
        summarise_facts('bot_facts')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO bot_facts (fact) VALUES (?)', (fact,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def load_bot_facts():
    """Load all facts about the bot."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT fact FROM bot_facts ORDER BY id')
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def extract_and_save_facts(conversation):
    """Extract and save both user facts and the bot's own facts from conversation."""

    # --- User facts ---
    user_facts = load_facts()
    existing_user = '\n'.join(user_facts) if user_facts else 'None yet.'

    user_extraction_prompt = f"""Your job is to extract ONLY concrete, specific facts about the user from this conversation.

                                VALID facts (save these):
                                - Name, age, location
                                - Specific hobbies or activities they mentioned doing
                                - Specific things they said they like or dislike
                                - Job, study field
                                - Specific life events they mentioned

                                INVALID facts (never save these):
                                - Vague personality traits ("user has a sense of humor")
                                - Things the assistant said or did
                                - Meta observations ("user enjoys conversation")
                                - Your own instructions or prompt text
                                - Anything that starts with "Existing facts"
                                - Numbered lists or bullet points as facts

                                Existing facts — do NOT repeat these:
                                {existing_user}

                                Conversation:
                                {conversation}

                                Reply with ONLY new valid facts, one plain sentence per line.
                                If nothing valid was found, reply with exactly: NOTHING"""

    try:
        response = requests.post('http://localhost:11434/api/chat', json={
            'model': MODEL,
            'messages': [{'role': 'user', 'content': user_extraction_prompt}],
            'stream': False,
            'options': {
                'num_gpu': 99,
                'num_ctx': 3072,
                'temperature': 0.3  # low temperature for factual extraction
            }
        })
        result = response.json()['message']['content'].strip()
        if result != 'NOTHING' and result.upper() != 'NOTHING':
            for line in result.split('\n'):
                line = line.strip()
                if line and line.upper() != 'NOTHING':
                    save_fact(line)
    except Exception as e:
        print(f'[Memory] Failed to extract user facts: {e}')

    # --- Bot facts ---
    bot_facts = load_bot_facts()
    existing_bot = '\n'.join(bot_facts) if bot_facts else 'None yet.'

    bot_extraction_prompt = f"""Your job is to extract ONLY specific things the assistant claimed about itself in this conversation.

                                VALID facts (save these):
                                - Specific preferences it invented ("I prefer silence over background noise")
                                - Specific opinions it expressed ("I think X is boring")
                                - Specific things it claimed to like or dislike
                                - Personal details it made up

                                INVALID facts (never save these):
                                - Things the user said
                                - Vague traits ("the assistant is sarcastic")
                                - AI-related statements ("I am a language model")
                                - Your own instructions or prompt text
                                - Anything that starts with "Existing facts"
                                - Numbered lists or bullet points as facts

                                Existing bot facts — do NOT repeat these:
                                {existing_bot}

                                Conversation:
                                {conversation}

                                Reply with ONLY new valid facts, one plain sentence per line.
                                If nothing valid was found, reply with exactly: NOTHING"""

    try:
        response = requests.post('http://localhost:11434/api/chat', json={
            'model': MODEL,
            'messages': [{'role': 'user', 'content': bot_extraction_prompt}],
            'stream': False,
            'options': {
                'num_gpu': 99,
                'num_ctx': 3072
            }
        })
        result = response.json()['message']['content'].strip()
        if result != 'NOTHING' and result.upper() != 'NOTHING':
            for line in result.split('\n'):
                line = line.strip()
                if line and line.upper() != 'NOTHING':
                    save_bot_fact(line)
    except Exception as e:
        print(f'[Memory] Failed to extract bot facts: {e}')
