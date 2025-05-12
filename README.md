# Nova

Nova is a personal AI assistant designed to help you with various tasks, including scheduling, searching, and managing your daily activities. Built with Python and Discord API, Nova integrates seamlessly into your workflow.

## Features

- **Discord Bot Integration**: Interact with Nova directly through Discord.
- **Scheduling**: Manage your daily schedule and receive reminders.
- **Search Functionality**: Perform web searches and retrieve relevant information.
- **Google Calendar Integration**: Sync your events and tasks with Google Calendar.
- **Customizable Commands**: Configure and extend Nova's capabilities to suit your needs.

## Project Structure

```
LICENSE
README.md
requirements.txt
src/
    config.yaml
    discord_bot.py
    assets/
        ai-agent-avatar.png
    cogs/
        admin_cog.py
        schedule_cog.py
        search_cog.py
    utils/
        config_loader.py
        discord_utils.py
        google_calendar.py
        llm_api.py
```

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/aj98-official/Nova.git
   cd Nova
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up your environment variables in a `.env` file:
   ```env
   DISCORD_BOT_TOKEN=your_discord_bot_token
   GOOGLE_CLIENT_ID=your_google_client_id
   GOOGLE_CLIENT_SECRET=your_google_client_secret
   ```

4. Configure the application by editing `src/config.yaml`.

## Usage

1. Run the Discord bot:
   ```bash
   python src/discord_bot.py
   ```

2. Interact with Nova through your Discord server.

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository.
2. Create a new branch for your feature or bug fix.
3. Commit your changes and push them to your fork.
4. Submit a pull request.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Discord API](https://discord.com/developers/docs/intro)
- [Python](https://www.python.org/)
- [Google Calendar API](https://developers.google.com/calendar)

---

Feel free to customize Nova to suit your needs and enjoy your personal AI assistant!
