import discord
import asyncio

async def send_long_message(ctx, text: str, prefix: str = ""):
    """Sends a potentially long message by splitting it into chunks of <=2000 chars."""
    MAX_LENGTH = 2000

    if not text:
        return

    # Prepend prefix to the text
    if prefix:
        text = prefix + text

    # If it fits in one message, just send it
    if len(text) <= MAX_LENGTH:
        await ctx.send(text)
        return

    while text:
        if len(text) <= MAX_LENGTH:
            await ctx.send(text)
            break

        # Try to split at last newline within limit
        split_pos = text.rfind('\n', 0, MAX_LENGTH)
        if split_pos <= 0:
            # Try to split at last space within limit
            split_pos = text.rfind(' ', 0, MAX_LENGTH)
        if split_pos <= 0:
            # Hard split at limit
            split_pos = MAX_LENGTH

        chunk = text[:split_pos]
        text = text[split_pos:].lstrip('\n')  # Remove leading newline from remainder

        if chunk.strip():
            await ctx.send(chunk)
            await asyncio.sleep(0.3)  # Small delay to avoid rate limits
