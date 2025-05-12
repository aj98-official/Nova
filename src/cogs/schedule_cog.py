import discord
from discord.ext import commands, tasks
import logging
import datetime
from dateutil import parser, tz
import asyncio

# Import utilities
from utils.google_calendar import (
    get_events_for_day,
    add_calendar_event,
    remove_calendar_event,
    parse_relative_date
)
from utils.discord_utils import send_long_message
from utils.config_loader import get_notify_channel_id, get_daily_summary_time_obj

logger = logging.getLogger(__name__)

class ScheduleCog(commands.Cog):
    def __init__(self, bot, calendar_service):
        self.bot = bot
        self.calendar_service = calendar_service # Get service from main bot
        self.last_viewed_events = {} # State specific to this cog instance
        self.notify_channel_id = get_notify_channel_id()
        self.daily_summary_time_obj = get_daily_summary_time_obj()

        # Start task if configured
        if self.calendar_service and self.notify_channel_id and self.daily_summary_time_obj:
            self.daily_schedule_summary.change_interval(time=self.daily_summary_time_obj)
            self.daily_schedule_summary.start()
            logger.info(f"ScheduleCog: Daily summary task started for {self.daily_summary_time_obj.strftime('%H:%M %Z')}.")
        elif not self.calendar_service:
             logger.warning("ScheduleCog: Daily summary task not started (Calendar service unavailable).")
        else:
             logger.warning("ScheduleCog: Daily summary task not started (notify_channel_id not configured).")

    def cog_unload(self):
        """Called when the cog is unloaded."""
        self.daily_schedule_summary.cancel()
        logger.info("ScheduleCog: Daily summary task cancelled.")

    async def get_notify_channel(self) -> discord.TextChannel | None:
        """Fetches the discord.TextChannel object for notifications."""
        if not self.notify_channel_id:
            return None
        try:
            channel_id_int = int(self.notify_channel_id)
            # Use bot.get_channel for potentially cached channel, fallback to fetch
            channel = self.bot.get_channel(channel_id_int) or await self.bot.fetch_channel(channel_id_int)
            if isinstance(channel, discord.TextChannel):
                return channel
            else:
                logger.error(f"ScheduleCog: Channel ID {self.notify_channel_id} is not a Text Channel.")
                return None
        except ValueError:
            logger.error(f"ScheduleCog: Invalid notify_channel_id '{self.notify_channel_id}'. It must be a number.")
            return None
        except discord.NotFound:
            logger.error(f"ScheduleCog: Could not find channel with ID {self.notify_channel_id}.")
            return None
        except discord.Forbidden:
            logger.error(f"ScheduleCog: Bot does not have permission to fetch channel {self.notify_channel_id}.")
            return None
        except discord.HTTPException as e:
            logger.error(f"ScheduleCog: HTTP error fetching channel {self.notify_channel_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"ScheduleCog: Unexpected error fetching channel {self.notify_channel_id}: {e}")
            return None

    # --- Background Task ---
    @tasks.loop(hours=24) # Initial interval, will be changed in __init__
    async def daily_schedule_summary(self):
        """Sends the daily schedule summary to the configured channel."""
        # Ensure loop runs only if service is available
        if not self.calendar_service:
             logger.warning("ScheduleCog: daily_schedule_summary skipped, calendar_service is None.")
             return

        logger.info("ScheduleCog: Running daily schedule summary task...")
        notify_channel = await self.get_notify_channel()

        if not notify_channel:
            logger.warning("ScheduleCog: Cannot send daily summary: Notify channel not found or configured.")
            return

        today = datetime.date.today()
        loop = asyncio.get_running_loop()
        try:
            summary_text, _ = await loop.run_in_executor(
                None, lambda: asyncio.run(get_events_for_day(self.calendar_service, today))
            )
        except Exception as e:
            logger.error(f"ScheduleCog: Error calling get_events_for_day via executor for daily summary: {e}")
            summary_text = "Error: Failed to fetch schedule details."

        if summary_text.startswith("Error:") or summary_text.startswith("An unexpected error"):
            message = f"⚠️ Could not fetch daily schedule summary. Error: {summary_text}"
        elif summary_text.startswith("No events found"):
            message = f"☀️ Good morning! No events scheduled for today ({today.strftime('%A, %B %d')})."
        else:
            summary_text = summary_text.replace(f"**Schedule for {today.strftime('%A, %B %d, %Y')}:**",
                                                f"🗓️ **Schedule for Today ({today.strftime('%A, %B %d')}):**")
            message = summary_text

        try:
            await send_long_message(notify_channel, message)
            logger.info(f"ScheduleCog: Sent daily summary to channel #{notify_channel.name}")
        except discord.Forbidden:
            logger.error(f"ScheduleCog: Cannot send message to channel #{notify_channel.name} ({self.notify_channel_id}). Check bot permissions.")
        except Exception as e:
            logger.error(f"ScheduleCog: Error sending notification to channel #{notify_channel.name}: {e}")

    @daily_schedule_summary.before_loop
    async def before_daily_summary(self):
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()
        logger.info("ScheduleCog: Bot is ready, daily_schedule_summary loop can start.")


    # --- Schedule Commands ---
    @commands.group(invoke_without_command=True, help="Manage your Google Calendar schedule.\nUse !help schedule <subcommand> for details.")
    async def schedule(self, ctx):
        """Base command for schedule management."""
        help_text = (
            "**Schedule Commands:**\n"
            "`!schedule view [day]` - Show schedule for today or a specific day (e.g., 'tomorrow', 'monday', 'April 25').\n"
            "`!schedule add \"<event title>\" <time/datetime> [duration_minutes]` - Add an event (e.g., `!schedule add \"Meeting\" \"3pm\" 60`).\n"
            "`!schedule remove <ID>` - Remove an event using the ID number shown by `!schedule view`."
        )
        await ctx.send(help_text)

    @schedule.command(name="view", help="Shows schedule for today or a specified day (e.g., 'tomorrow', 'monday', 'April 25').")
    async def schedule_view(self, ctx, *, day_str: str = "today"):
        """Shows schedule from Google Calendar for a given day."""
        logger.info(f"ScheduleCog: Received schedule view request from {ctx.author} for '{day_str}'")
        if not self.calendar_service:
            await ctx.send("Error: Google Calendar connection is not available.")
            return

        target_date = parse_relative_date(day_str)
        if not target_date:
            await ctx.send(f"Error: Could not understand the date '{day_str}'. Try 'today', 'tomorrow', 'monday', 'April 25', etc.")
            return

        await ctx.send(f"Fetching schedule for {target_date.strftime('%A, %B %d, %Y')} from Google Calendar...")

        loop = asyncio.get_running_loop()
        try:
            summary_text, events_details = await loop.run_in_executor(
                None, lambda: asyncio.run(get_events_for_day(self.calendar_service, target_date))
            )
        except Exception as e:
            logger.error(f"ScheduleCog: Error calling get_events_for_day via executor: {e}")
            await ctx.send("Sorry, an error occurred while fetching the schedule.")
            return

        self.last_viewed_events[ctx.author.id] = events_details # Store in cog instance state
        await send_long_message(ctx, summary_text)

    @schedule.command(name="add", help="Adds event. Ex: !schedule add \"Meeting\" \"3pm\" 60")
    async def schedule_add(self, ctx, summary: str, time_str: str, duration_minutes: int = 60):
        """Adds an event to Google Calendar."""
        logger.info(f"ScheduleCog: Received schedule add request from {ctx.author}: {summary}, {time_str}, {duration_minutes}")
        if not self.calendar_service:
            await ctx.send("Error: Google Calendar connection is not available.")
            return

        try:
            start_dt = parser.parse(time_str)
            local_tz = tz.tzlocal()
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=local_tz)
            else:
                start_dt = start_dt.astimezone(local_tz)

            end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)

            await ctx.send(f"Adding event '{summary}' to Google Calendar for {start_dt.strftime('%Y-%m-%d %I:%M %p %Z')}...")

            loop = asyncio.get_running_loop()
            try:
                result = await loop.run_in_executor(
                    None, lambda: asyncio.run(add_calendar_event(self.calendar_service, summary, start_dt, end_dt))
                )
            except Exception as e:
                logger.error(f"ScheduleCog: Error calling add_calendar_event via executor: {e}")
                await ctx.send("Sorry, an error occurred while adding the event.")
                return

            await ctx.send(result)

        except parser.ParserError:
            logger.warning(f"ScheduleCog: Failed to parse time string: {time_str}")
            await ctx.send(f"Error: Could not understand the time '{time_str}'. Please use formats like '3pm', '15:00', 'tomorrow 10am', '2025-04-20 14:30'.")
        except ValueError as ve:
            logger.warning(f"ScheduleCog: Value error during parsing or calculation: {ve}")
            await ctx.send(f"Error processing time or duration. Please check your input: {ve}")
        except Exception as e:
            logger.error(f"ScheduleCog: Unexpected error in schedule add command: {e}", exc_info=True)
            await ctx.send("An unexpected error occurred while adding the event.")

    @schedule.command(name="remove", help="Removes event using ID from `!schedule view` (e.g., !schedule remove 2).")
    async def schedule_remove(self, ctx, event_index: int):
        """Removes an event from Google Calendar using the index from the last view."""
        logger.info(f"ScheduleCog: Received schedule remove request from {ctx.author} for index {event_index}")

        if not self.calendar_service:
            await ctx.send("Error: Google Calendar connection is not available.")
            return

        user_last_events = self.last_viewed_events.get(ctx.author.id)
        if not user_last_events:
            await ctx.send("Please use `!schedule view` first to see the list of events and their IDs.")
            return

        try:
            target_index = event_index - 1
            if 0 <= target_index < len(user_last_events):
                event_id_to_remove, time_str, summary = user_last_events[target_index]

                await ctx.send(f"Attempting to remove event: [{event_index}] {time_str}: {summary} (ID: {event_id_to_remove[:6]}...)...")

                loop = asyncio.get_running_loop()
                try:
                    result = await loop.run_in_executor(
                        None, lambda: asyncio.run(remove_calendar_event(self.calendar_service, event_id_to_remove))
                    )
                except Exception as e:
                    logger.error(f"ScheduleCog: Error calling remove_calendar_event via executor: {e}")
                    await ctx.send("Sorry, an error occurred while removing the event.")
                    return

                await ctx.send(result)
            else:
                await ctx.send(f"Error: Invalid ID '{event_index}'. Please use `!schedule view` and provide a valid number from the list.")

        except ValueError:
            await ctx.send("Error: Please provide the numerical ID shown by `!schedule view`.")
        except Exception as e:
            logger.error(f"ScheduleCog: Unexpected error in schedule remove command: {e}", exc_info=True)
            await ctx.send("An unexpected error occurred while removing the event.")


async def setup(bot, calendar_service=None):
    """Allows the cog to be loaded by the bot, passing the calendar service."""
    if calendar_service is None:
         logger.error("ScheduleCog requires the calendar_service to be passed during setup.")
         # Or raise an exception
         return
    await bot.add_cog(ScheduleCog(bot, calendar_service))
    logger.info("ScheduleCog loaded.")
