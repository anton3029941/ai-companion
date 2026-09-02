import discord
from discord.ext import commands, tasks
import methods
import memory
import tts
import os
import asyncio
import random
from dotenv import load_dotenv
from voice_listener import VoiceListener

load_dotenv()
token = os.getenv('DISCORD_TOKEN')
owner_user_id = int(os.getenv('OWNER_USER_ID', 0))

# Initialize database on startup
memory.init_db()

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

INITIATION_PROMPTS = [
    "You just had a random passing thought. Send the user one short message about it. Don't introduce yourself.",
    "Something mundane just caught your attention. Tell the user in one sentence without over-explaining.",
    "You have a mild opinion about something trivial. Share it with the user in one sentence.",
    "Send the user a very casual one-line check-in. Keep it brief.",
    "You're bored. Message the user about it in under 8 words.",
    "Send the user an unprompted lighthearted comment about something you know about them. One sentence, no setup.",
]

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    print('Bot is online.')
    random_initiation.start()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if not isinstance(message.channel, discord.DMChannel):
        return

    async with message.channel.typing():
        response = await asyncio.to_thread(
            methods.generate_response,
            message.channel.id,
            message.content
        )

    await message.channel.send(response)
    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member, before, after):
    """Auto-join when the owner joins a voice channel, leave when they leave."""
    if member.id != owner_user_id:
        return

    # Owner joined a voice channel
    if after.channel and not before.channel:
        await join_voice(after.channel)

    # Owner left voice
    elif not after.channel and before.channel:
        guild = before.channel.guild
        if guild.voice_client:
            try:
                guild.voice_client.stop_recording()
            except Exception:
                pass  # ignore if not recording
            await guild.voice_client.disconnect()
            print("[Voice] Disconnected.")

    # Owner switched channels
    elif after.channel and before.channel and after.channel != before.channel:
        guild = after.channel.guild
        if guild.voice_client:
            await guild.voice_client.move_to(after.channel)

async def join_voice(channel):
    print(f"[Voice] Joining {channel.name}")

    # Prevent double connection attempts
    if channel.guild.voice_client is not None:
        print("[Voice] Already connected, skipping.")
        return

    try:
        voice_client = await channel.connect(timeout=60.0, reconnect=False)
        await asyncio.sleep(3)
        print(f"[Voice] is_connected: {voice_client.is_connected()}")

        if voice_client.is_connected():
            voice_client.start_recording(
                discord.sinks.WaveSink(),
                finished_callback,
                channel
            )
            print("[Voice] Recording started.")
        else:
            print("[Voice] Still not connected.")

    except Exception as e:
        print(f"[Voice] Error: {type(e).__name__}: {e}")

async def finished_callback(sink, channel, *args):
    """Called when recording stops — transcribe and respond."""
    print("[Voice] Processing audio...")
    for user_id, audio in sink.audio_data.items():
        if user_id == owner_user_id:
            audio_bytes = audio.file.read()
            listener = VoiceListener()
            text = listener.process_audio(audio_bytes)
            if text:
                print(f"[Voice] Heard: {text}")
                vc = channel.guild.voice_client
                if vc:
                    await handle_voice_message(vc, text)

async def handle_voice_message(voice_client, text):
    """Generate response and play TTS."""
    print(f"[Voice] Generating response for: {text}")

    response = await asyncio.to_thread(
        methods.generate_response,
        voice_client.channel.guild.id,
        text
    )
    print(f"[Voice] Response: {response}")

    # Convert to speech
    audio_file = await tts.synthesize(response)

    # Play in voice channel
    if voice_client.is_connected():
        source = discord.FFmpegPCMAudio(audio_file)
        voice_client.play(source)

        # Wait for playback to finish
        while voice_client.is_playing():
            await asyncio.sleep(0.1)

@tasks.loop(minutes=30)
async def random_initiation():
    random_initiation.change_interval(minutes=random.randint(30, 180))

    if random.random() > 0.4:
        return

    if owner_user_id == 0:
        print("[Bot] No user ID set — skipping.")
        return

    try:
        user = await bot.fetch_user(owner_user_id)
        dm_channel = await user.create_dm()
        initiation_prompt = random.choice(INITIATION_PROMPTS)

        async with dm_channel.typing():
            response = await asyncio.to_thread(
                methods.generate_response,
                dm_channel.id,
                f"[SYSTEM: {initiation_prompt}]"
            )

        await dm_channel.send(response)
        print(f"[Bot] Initiated DM: {response}")

    except Exception as e:
        print(f"[Bot] Failed to initiate DM: {e}")

@random_initiation.before_loop
async def before_initiation():
    await bot.wait_until_ready()
    delay = random.randint(600, 3600)
    print(f"[Bot] First initiation check in {delay // 60} minutes.")
    await asyncio.sleep(delay)

bot.run(token)
