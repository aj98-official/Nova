import discord
from discord.ext import commands
import logging
import asyncio

# Import the specific function needed from google_calendar utility
from utils.google_calendar import run_google_auth_flow
from utils.config_loader import get_llm_command_configs

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

    @commands.command(name="nova", help="Start a persistent chat with your AI assistant. Type '!nova quit' to end the session.")
    async def nova(self, ctx, *, instruction: str = None):
        """
        Starts a persistent chat session with the AI assistant. Maintains context, allows normal conversation,
        clarifies ambiguous requests, and only breaks into commands when a clear actionable request is made.
        Ends session on '!nova quit'.
        """
        from utils.llm_api import get_llm_response
        import asyncio
        import copy

        # Load all configurable values from config at the very top of the function
        llm_configs = get_llm_command_configs()
        nova_cfg = llm_configs.get('nova', {})
        api_key = nova_cfg.get('api_key')
        api_url = nova_cfg.get('api_url')
        model_name = nova_cfg.get('model_name')
        system_prompt = nova_cfg.get('system_prompt')
        summarization_prompt = nova_cfg.get('summarization_prompt')
        command_confirmation_prompt = nova_cfg.get('command_confirmation_prompt')
        session_greeting = nova_cfg.get('session_greeting')
        session_end_message = nova_cfg.get('session_end_message')
        session_timeout_message = nova_cfg.get('session_timeout_message')
        summarizing_context_message = nova_cfg.get('summarizing_context_message')
        all_commands_executed_message = nova_cfg.get('all_commands_executed_message')
        executing_commands_message = nova_cfg.get('executing_commands_message')
        llm_thinking_message = nova_cfg.get('llm_thinking_message')
        llm_error_message = nova_cfg.get('llm_error_message')
        missing_system_prompt_message = nova_cfg.get('missing_system_prompt_message')
        missing_summarization_prompt_message = nova_cfg.get('missing_summarization_prompt_message')
        missing_confirmation_prompt_message = nova_cfg.get('missing_confirmation_prompt_message')
        max_input_tokens = nova_cfg.get('max_input_tokens')
        max_chars = nova_cfg.get('max_chars')

        # Session state per user (in-memory, can be moved to persistent storage if needed)
        if not hasattr(self, 'nova_sessions'):
            self.nova_sessions = {}
        user_id = ctx.author.id
        
        # Handle quit command first, before any session management
        if instruction and instruction.strip().lower() in ['quit', '!nova quit']:
            if user_id in self.nova_sessions:
                del self.nova_sessions[user_id]
            await ctx.send(session_end_message or "Nova session ended. See you next time!")
            return
        
        # Initialize session if it doesn't exist
        if user_id not in self.nova_sessions:
            self.nova_sessions[user_id] = {
                'history': []
            }
            await ctx.send(session_greeting or "Hi! I'm Nova, your personal assistant. How can I help you today? (Type '!nova quit' to end this session.)")
            if not instruction:
                def first_check(m):
                    return m.author == ctx.author and m.channel == ctx.channel
                try:
                    first_msg = await self.bot.wait_for('message', check=first_check, timeout=120)
                    instruction = first_msg.content
                except asyncio.TimeoutError:
                    await ctx.send(session_timeout_message or "Session timed out. Please start again with !nova if you need me.")
                    if user_id in self.nova_sessions:
                        del self.nova_sessions[user_id]
                    return

        # Main chat loop
        while True:
            # Check if session still exists (might have been deleted by timeout/quit)
            if user_id not in self.nova_sessions:
                return
                
            # Add user message to history
            self.nova_sessions[user_id]['history'].append({"role": "user", "content": instruction})

            # --- Hybrid: Summarize oldest context if over max, then trim ---
            try:
                MAX_CHARS = int(max_chars)
            except Exception:
                MAX_CHARS = 48000
            system_chars = len(system_prompt)
            trimmed_history = []
            total_chars = system_chars
            # Only keep the most recent messages that fit within the limit
            for msg in reversed(self.nova_sessions[user_id]['history']):
                msg_chars = len(msg.get('content', '')) + len(msg.get('role', ''))
                if total_chars + msg_chars > MAX_CHARS:
                    break
                trimmed_history.insert(0, msg)
                total_chars += msg_chars
            # If we had to trim, summarize the dropped context
            dropped_count = len(self.nova_sessions[user_id]['history']) - len(trimmed_history)
            if dropped_count > 0:
                dropped_msgs = self.nova_sessions[user_id]['history'][:dropped_count]
                dropped_text = '\n'.join(f"{m['role']}: {m['content']}" for m in dropped_msgs)
                await ctx.send(summarizing_context_message or "Summarizing older context for continuity...")
                summary_prompt = summarization_prompt + dropped_text
                summary = await get_llm_response(api_key, api_url, model_name, "You are a helpful assistant summarizer.", summary_prompt)
                if summary and not summary.startswith("Error"):
                    trimmed_history.insert(0, {"role": "system", "content": f"Summary of earlier conversation: {summary}"})
                else:
                    trimmed_history.insert(0, {"role": "system", "content": "Summary of earlier conversation omitted due to summarization error."})
            self.nova_sessions[user_id]['history'] = trimmed_history

            if not system_prompt:
                await ctx.send(missing_system_prompt_message or "Nova's system_prompt is missing from config.")
                return
            if not summarization_prompt:
                await ctx.send(missing_summarization_prompt_message or "Nova's summarization_prompt is missing from config.")
                return
            if not command_confirmation_prompt:
                await ctx.send(missing_confirmation_prompt_message or "Nova's command_confirmation_prompt is missing from config.")
                return

            # Build message history for LLM
            messages = [
                {"role": "system", "content": system_prompt}
            ] + self.nova_sessions[user_id]['history']

            # Call LLM
            await ctx.send(llm_thinking_message or "Nova is thinking...")
            llm_response = await get_llm_response(api_key, api_url, model_name, system_prompt, instruction)
            if not llm_response or llm_response.startswith("Error"):
                await ctx.send((llm_error_message or "LLM error: {error}").replace('{error}', llm_response or 'Unknown error'))
                return

            # Add assistant response to history
            if user_id not in self.nova_sessions:
                return
            self.nova_sessions[user_id]['history'].append({"role": "assistant", "content": llm_response})

            # If the LLM response looks like a command list, ask for confirmation
            lines = [line.strip() for line in llm_response.strip().splitlines() if line.strip()]
            # Check if any line starts with ! (indicating commands)
            is_command_list = any(line.startswith('!') for line in lines)
            
            if is_command_list:
                # Extract only the command lines
                command_lines = [line for line in lines if line.startswith('!')]
            if is_command_list:
                # Extract only the command lines
                command_lines = [line for line in lines if line.startswith('!')]
                # Use the command lines for confirmation message
                commands_text = '\n'.join(command_lines)
                confirmation_message = command_confirmation_prompt.replace('{commands}', commands_text)
                await ctx.send(confirmation_message)
                def confirm_check(m):
                    return m.author == ctx.author and m.channel == ctx.channel
                try:
                    reply = await self.bot.wait_for('message', check=confirm_check, timeout=90)
                except asyncio.TimeoutError:
                    await ctx.send(session_timeout_message or "Session timed out. Please start again with !nova if you need me.")
                    if user_id in self.nova_sessions:
                        del self.nova_sessions[user_id]
                    return
                if reply.content.strip().lower() in ["yes", "y", "confirm"]:
                    await ctx.send((executing_commands_message or "Executing {count} commands...").replace('{count}', str(len(command_lines))))
                    for cmd in command_lines:
                        fake_message = copy.copy(ctx.message)
                        if not cmd.startswith(ctx.prefix):
                            fake_message.content = ctx.prefix + cmd.lstrip('!')
                        else:
                            fake_message.content = cmd
                        await self.bot.process_commands(fake_message)
                    await ctx.send(all_commands_executed_message or "All commands executed. What else can I help you with?")
                elif reply.content.strip().lower() in ["!nova quit", "quit"]:
                    await ctx.send(session_end_message or "Nova session ended. See you next time!")
                    if user_id in self.nova_sessions:
                        del self.nova_sessions[user_id]
                    return
                else:
                    if user_id not in self.nova_sessions:
                        return
                    self.nova_sessions[user_id]['history'].append({"role": "user", "content": reply.content})
                    instruction = reply.content
                    continue
            else:
                # Just chat normally
                await ctx.send(llm_response)
                def chat_check(m):
                    return m.author == ctx.author and m.channel == ctx.channel
                try:
                    next_msg = await self.bot.wait_for('message', check=chat_check, timeout=300000)
                except asyncio.TimeoutError:
                    await ctx.send(session_timeout_message or "Session timed out. Please start again with !nova if you need me.")
                    if user_id in self.nova_sessions:
                        del self.nova_sessions[user_id]
                    return
                instruction = next_msg.content
                
                # Check if the new instruction is a quit command
                if instruction.strip().lower() in ['!nova quit', 'quit']:
                    await ctx.send(session_end_message or "Nova session ended. See you next time!")
                    if user_id in self.nova_sessions:
                        del self.nova_sessions[user_id]
                    return


async def setup(bot):
    """Allows the cog to be loaded by the bot."""
    await bot.add_cog(AdminCog(bot))
    logger.info("AdminCog loaded.")
