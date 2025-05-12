import discord
from discord.ext import commands
import logging
import asyncio

# Import the specific function needed from google_calendar utility
from utils.google_calendar import run_google_auth_flow

logger = logging.getLogger(__name__)

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="reauth_google", help="Starts the Google OAuth flow to get a new refresh token (Owner only).")
    @commands.is_owner() # Restricts this command to the bot owner specified in config or application info
    async def reauth_google(self, ctx):
        """Initiates the Google OAuth flow and DMs the owner the new refresh token."""
        logger.info(f"Owner {ctx.author} initiated Google re-authorization flow.")
        await ctx.send("Attempting Google re-authorization. Please check the console output and follow the browser instructions. I will DM you the new refresh token if successful.")

        try:
            # Run the authorization flow function
            new_creds = await run_google_auth_flow()

            if new_creds and new_creds.refresh_token:
                success_message = (
                    f"✅ Google authorization successful!\n\n"
                    f"Please **update your configuration** (config.yaml or environment variable) with the following refresh token:\n\n"
                    f"```\n{new_creds.refresh_token}\n```\n\n"
                    f"You will need to **restart the bot** after updating the configuration."
                )
                try:
                    await ctx.author.send(success_message) # Send token via DM
                    await ctx.send("Sent the new refresh token via DM.")
                    logger.info(f"Successfully sent new refresh token to owner {ctx.author}.")
                except discord.Forbidden:
                    logger.warning(f"Could not DM owner {ctx.author}. Sending token to channel instead (less secure).")
                    await ctx.send(success_message) # Fallback to channel if DMs fail
                except Exception as e:
                     logger.error(f"Failed to send refresh token to owner {ctx.author}: {e}")
                     await ctx.send("Authorization successful, but failed to send you the token via DM. Please check the console logs for the token (printed during the flow).")

            else:
                logger.error("Google authorization flow completed but failed to obtain a refresh token.")
                await ctx.send("❌ Google authorization failed. Could not obtain a new refresh token. Check console logs for details.")

        except Exception as e:
            logger.error(f"An unexpected error occurred during the reauth_google command: {e}", exc_info=True)
            await ctx.send("❌ An unexpected error occurred during the re-authorization process. Check console logs.")

    @reauth_google.error
    async def reauth_google_error(self, ctx, error):
        """Error handler specifically for the reauth_google command."""
        if isinstance(error, commands.NotOwner):
            await ctx.send("Sorry, only the bot owner can use this command.")
        else:
            # Log other errors related to this command if needed
            logger.error(f"Error in reauth_google command: {error}", exc_info=True)
            await ctx.send("An error occurred processing the reauth_google command.")


async def setup(bot):
    """Allows the cog to be loaded by the bot."""
    await bot.add_cog(AdminCog(bot))
    logger.info("AdminCog loaded.")
