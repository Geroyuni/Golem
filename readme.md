# Golem
Simple bot that provides support commands for the Parsec server.

## Running your own instance
### Requirements
* [Python 3.10+](https://www.python.org/downloads/)
* `pip install -r requirements.txt`

### Setup
* Create a `token_.py` file containing a variable named token, with your bot token
* It'll be necessary to add an on_ready function with `await self.tree.sync()` to the bot class at least once. After which, you can sync changes with the owner command

### Running
* Run the bot with `python3 bot.py`
