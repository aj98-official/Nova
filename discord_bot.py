import discord
from discord.ext import commands
import os
import logging
import asyncio

# Import utilities
from utils import config_loader  # Import the module
from utils.google_calendar import get_calendar_service  # Only need the service initializer here

# --- Basic Logging Setup ---
# Configure logging early
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Load Configuration ---
# Use the utility function to load config
config_loader.load_config()
BOT_TOKEN = config_loader.get_bot_token()  # Get token after loading

# --- Global Services ---
# Initialize calendar service (can potentially block, run in executor)
# We'll do this within on_ready to ensure the event loop is running
calendar_service = None

# --- Bot Setup ---
# Intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

# Create the bot instance
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Cogs to Load ---
# List of cogs (relative path from this file)
INITIAL_EXTENSIONS = [
    'cogs.search_cog',
    'cogs.schedule_cog',
    'cogs.admin_cog'  # ADDED: Load the new admin cog
]

# --- Bot Events ---
@bot.event
async def on_ready():
    """Called when the bot is ready and connected."""
    global calendar_service
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    logger.info(f"Discord.py version: {discord.__version__}")

    # --- Initialize Services requiring async context or executor ---
    logger.info("Attempting to initialize Google Calendar service...")
    loop = asyncio.get_running_loop()
    try:
        # Run blocking IO in executor
        calendar_service = await loop.run_in_executor(None, get_calendar_service)
        if calendar_service:
            logger.info("Google Calendar service initialized successfully.")
        else:
            # Log error, but don't notify owner here as get_calendar_service now logs instructions
            logger.error("Google Calendar service failed to initialize. Schedule features disabled. Check logs for instructions.")

    except Exception as e:
        logger.critical(f"CRITICAL: Failed to run get_calendar_service in executor: {e}")
        calendar_service = None  # Ensure it's None

    # --- Load Cogs ---
    logger.info("Loading cogs...")
    for extension in INITIAL_EXTENSIONS:
        try:
            # Pass calendar service specifically to schedule_cog during setup
            if extension == 'cogs.schedule_cog':
                # Dynamically get the setup function and call it with the service
                ext_module = __import__(extension, fromlist=['setup'])
                await ext_module.setup(bot, calendar_service=calendar_service)
            else:
                await bot.load_extension(extension)
        except commands.ExtensionNotFound:
            logger.error(f"Could not find extension: {extension}")
        except commands.ExtensionAlreadyLoaded:
            logger.warning(f"Extension already loaded: {extension}")
        except commands.NoEntryPointError:
            logger.error(f"Extension '{extension}' does not have a setup function.")
        except commands.ExtensionFailed as e:
            logger.error(f"Failed to load extension {extension}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"An unexpected error occurred loading extension {extension}: {e}", exc_info=True)

    logger.info("Bot is ready.")


@bot.event
async def on_command_error(ctx, error):
    """Global command error handler."""
    if isinstance(error, commands.CommandNotFound):
        pass  # Or log it: logger.debug(f"Command not found: {ctx.message.content}")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Oops! You missed an argument for the `{ctx.command}` command. Try `!help {ctx.command}`.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"Hmm, I didn't understand one of the arguments you provided for `{ctx.command}`. Try `!help {ctx.command}`.")
    elif isinstance(error, commands.CommandInvokeError):
        logger.error(f"Error invoking command '{ctx.command}': {error.original}", exc_info=error.original)
        await ctx.send(f"An internal error occurred while running the command `{ctx.command}`. Please check the logs.")
    elif isinstance(error, commands.CheckFailure):
        logger.warning(f"Check failed for command '{ctx.command}' by user {ctx.author}: {error}")
    else:
        logger.error(f"Unhandled command error in '{ctx.command}': {error}", exc_info=True)
        await ctx.send("An unexpected error occurred.")


# --- Run the Bot ---
if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.critical("CRITICAL: BOT_TOKEN not found after config load. Bot cannot start.")
    else:
        logger.info("Starting bot...")
        try:
            bot.run(BOT_TOKEN, log_handler=None)  # Use our basicConfig logger
        except discord.LoginFailure:
            logger.critical("CRITICAL: Failed to log in. Check if BOT_TOKEN is correct.")
        except Exception as e:
            logger.critical(f"CRITICAL: An error occurred during bot execution: {e}", exc_info=True)