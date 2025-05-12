import discord
from discord.ext import commands
import logging
import asyncio

# Import utilities
from utils.llm_api import get_llm_response
from utils.discord_utils import send_long_message
from utils.config_loader import get_llm_command_configs, is_llm_command_configured

logger = logging.getLogger(__name__)

class SearchCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.llm_command_configs = get_llm_command_configs()
        self.search_configured = is_llm_command_configured('search')
        if self.search_configured:
             search_cfg = self.llm_command_configs.get('search', {})
             logger.info(f"SearchCog: LLM 'search' command configured: Provider={search_cfg.get('provider_name')}, Model={search_cfg.get('model_name')}")
        else:
             logger.warning("SearchCog: LLM 'search' command is not fully configured.")

    @commands.command(name="search", help="Ask the LLM to research a topic with fact-checking.")
    async def search(self, ctx, *, query: str):
        """Researches a topic using the configured LLM."""
        logger.info(f"SearchCog: Received search query from {ctx.author} (ID: {ctx.author.id}): {query}")

        if not self.search_configured:
            await ctx.send("Sorry, the LLM search functionality is not configured.")
            return

        search_config = self.llm_command_configs.get('search', {})
        provider_name = search_config.get('provider_name', 'LLM')
        model_name = search_config.get('model_name', 'default')
        api_key = search_config.get('api_key')
        api_url = search_config.get('api_url')
        system_prompt = search_config.get('system_prompt', '')

        # Redundant check, but safe
        if not all([api_key, api_url, model_name, system_prompt]):
            logger.error("SearchCog: Search command triggered, but configuration is incomplete.")
            await ctx.send("Sorry, the search configuration is incomplete.")
            return

        await ctx.send(f"Asking {provider_name} ({model_name}): '{query}'...")

        loop = asyncio.get_running_loop()
        try:
            api_response = await loop.run_in_executor(
                None,
                lambda: asyncio.run(get_llm_response(
                    api_key,
                    api_url,
                    model_name,
                    system_prompt,
                    query
                ))
            )
        except Exception as e:
            logger.error(f"SearchCog: Error calling get_llm_response via executor: {e}")
            await ctx.send("Sorry, an error occurred while contacting the LLM.")
            return

        if api_response:
            if api_response.startswith("Error:"):
                await ctx.send(api_response)
            else:
                await send_long_message(ctx, api_response)
        else:
            await ctx.send("Sorry, an unexpected issue occurred while getting the response.")

async def setup(bot):
    """Allows the cog to be loaded by the bot."""
    await bot.add_cog(SearchCog(bot))
    logger.info("SearchCog loaded.")
