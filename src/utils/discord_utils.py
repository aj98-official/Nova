import discord # Add discord import
import asyncio # Add asyncio import

async def send_long_message(ctx: discord.ext.commands.Context, text: str, prefix: str = ""):
    """Sends a potentially long message by splitting it into chunks."""
    MAX_LENGTH = 2000
    current_pos = 0
    first_message = True

    while current_pos < len(text):
        message_prefix = prefix if first_message else ""
        # Calculate remaining space in the chunk, accounting for the prefix
        remaining_space = MAX_LENGTH - len(message_prefix)

        # Determine the end position for the current chunk
        end_pos = current_pos + remaining_space
        # Ensure we don't exceed the text length
        end_pos = min(end_pos, len(text))

        # Find the last newline or space within the chunk to avoid splitting mid-word/sentence if possible
        split_pos = text.rfind('\n', current_pos, end_pos)
        if split_pos == -1 or split_pos <= current_pos:
             split_pos = text.rfind(' ', current_pos, end_pos)
             if split_pos == -1 or split_pos <= current_pos:
                  split_pos = end_pos

        # Extract the chunk
        chunk = text[current_pos:split_pos].strip()
        if not chunk:
            chunk = text[current_pos:end_pos]

        # Send the chunk
        if chunk:
            await ctx.send(f"{message_prefix}{chunk}")

        # Update position for the next chunk
        current_pos = split_pos if chunk == text[current_pos:split_pos].strip() else end_pos

        first_message = False
        # Optional: Add a small delay
        # await asyncio.sleep(0.1)
