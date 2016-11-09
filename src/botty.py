#!/usr/bin/env python3

import sys, logging
from collections import deque

from bot import SlackBot

# process settings
#logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logging.basicConfig(filename="botty.log", level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

def initialize_plugins(botty):
    """Import, register, and initialize Botty plugins. Edit the body of this function to change which plugins are loaded."""
    from plugins.arithmetic import ArithmeticPlugin; botty.register_plugin(ArithmeticPlugin(botty))
    from plugins.timezones import TimezonesPlugin; botty.register_plugin(TimezonesPlugin(botty))
    from plugins.poll import PollPlugin; botty.register_plugin(PollPlugin(botty))
    from plugins.wiki import WikiPlugin; botty.register_plugin(WikiPlugin(botty))
    from plugins.haiku import HaikuPlugin; botty.register_plugin(HaikuPlugin(botty))
    from plugins.personality import PersonalityPlugin; botty.register_plugin(PersonalityPlugin(botty))
    from plugins.events import EventsPlugin; botty.register_plugin(EventsPlugin(botty))
    from plugins.now_i_am_dude import NowIAmDudePlugin; botty.register_plugin(NowIAmDudePlugin(botty))
    from plugins.generate_text import GenerateTextPlugin; botty.register_plugin(GenerateTextPlugin(botty))
    from plugins.big_text import BigTextPlugin; botty.register_plugin(BigTextPlugin(botty))
    from plugins.uw_courses import UWCoursesPlugin; botty.register_plugin(UWCoursesPlugin(botty))
    from plugins.spaaace import SpaaacePlugin; botty.register_plugin(SpaaacePlugin(botty))
    from plugins.agario import AgarioPlugin; botty.register_plugin(AgarioPlugin(botty))
    from plugins.snek import SnekPlugin; botty.register_plugin(SnekPlugin(botty))

if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1] in {"--help", "-h", "-?"}):
    print("Usage: {} --help".format(sys.argv[0]))
    print("    Show this help message")
    print("Usage: {}".format(sys.argv[0]))
    print("    Start the Botty chatbot for Slack in testing mode with a console chat interface")
    print("Usage: {} SLACK_BOT_TOKEN".format(sys.argv[0]))
    print("    Start the Botty chatbot for the Slack chat associated with SLACK_BOT_TOKEN, and enter the in-process Python REPL")
    print("    SLACK_BOT_TOKEN is a Slack API token (can be obtained from https://api.slack.com/)")
    sys.exit(1)

DEBUG = len(sys.argv) < 2
if DEBUG:
    from bot import SlackDebugBot as SlackBot
    SLACK_TOKEN = ""
    print("No Slack API token specified in command line arguments; starting in local debug mode...")
else:
    SLACK_TOKEN = sys.argv[1]

class Botty(SlackBot):
    def __init__(self, token):
        super().__init__(token)
        self.plugins = []
        self.last_message_channel_id = None
        self.last_message_timestamp = None
        self.recent_events = deque(maxlen=2000) # store the last 2000 events

    def register_plugin(self, plugin_instance):
        self.plugins.append(plugin_instance)

    def on_step(self):
        for plugin in self.plugins:
            if plugin.on_step(): break

    def on_message(self, message):
        self.logger.debug("received message message {}".format(message))
        timestamp = self.get_message_timestamp(message)
        if timestamp: self.last_message_timestamp = timestamp

        # save channel to use with response
        channel = self.get_message_channel(message)
        if channel: self.last_message_channel_id = channel

        # ignore bot messages
        sender = self.get_message_sender(message)
        if sender is not None and self.get_user_is_bot(sender): return

        # save recent message events
        if message.get("type") not in {"ping", "pong", "presence_change", "user_typing", "reconnect_url"}:
            self.recent_events.append(message)

        for plugin in self.plugins:
            if plugin.on_message(message):
                self.logger.info("message handled by {}: {}".format(plugin.__class__.__name__, message))
                break

    def get_message_text(self, message):
        """Returns the text value of `message` if it is a valid text message, or `None` otherwise"""
        if message.get("type") == "message" and isinstance(message.get("ts"), str):
            if isinstance(message.get("text"), str) and isinstance(message.get("user"), str): # normal message
                return self.server_text_to_sendable_text(message["text"])
            if message.get("subtype") == "message_changed" and isinstance(message.get("message"), dict) and isinstance(message["message"].get("user"), str) and isinstance(message["message"].get("text"), str): # edited message
                return self.server_text_to_sendable_text(message["message"]["text"])
        return None

    def get_message_timestamp(self, message):
        """Returns the timestamp of `message` if there is one, or `None` otherwise"""
        if isinstance(message.get("ts"), str): return message["ts"]
        return None

    def get_message_channel(self, message):
        """Returns the ID of the channel containing `message` if there is one, or `None` otherwise"""
        if isinstance(message.get("channel"), str): return message["channel"]
        return None

    def get_message_sender(self, message):
        """Returns the ID of the user who sent `message` if there is one, or `None` otherwise"""
        if isinstance(message.get("user"), str): return message["user"] # normal message
        if message.get("subtype") == "message_changed" and isinstance(message.get("message"), dict) and isinstance(message["message"].get("user"), str): # edited message
            return message["message"]["user"]
        return None

    def respond(self, sendable_text):
        """Say `sendable_text` in the channel that most recently received a message, returning the message ID (unique within each `SlackBot` instance)."""
        assert self.last_message_channel_id is not None, "No message to respond to"
        return self.say(self.last_message_channel_id, sendable_text)

    def respond_complete(self, sendable_text):
        """Say `sendable_text` in the channel that most recently received a message, waiting until the message is successfully sent, returning the message timestamp."""
        assert self.last_message_channel_id is not None, "No message to respond to"
        return self.say_complete(self.last_message_channel_id, sendable_text)

    def reply(self, emoticon):
        """React with `emoticon` to the most recently received message."""
        assert self.last_message_channel_id is not None and self.last_message_timestamp is not None, "No message to reply to"
        return self.react(self.last_message_channel_id, self.last_message_timestamp, emoticon)

    def unreply(self, emoticon):
        """Remove `emoticon` reaction from the most recently received message."""
        assert self.last_message_channel_id is not None and self.last_message_timestamp is not None, "No message to unreply to"
        return self.unreact(self.last_message_channel_id, self.last_message_timestamp, emoticon)

botty = Botty(SLACK_TOKEN)
initialize_plugins(botty)

# start administrator console in production mode
if not DEBUG:
    def say(channel, text):
        """Say `text` in `channel` where `text` is a sendable text string and `channel` is a channel name like #general."""
        botty.say(botty.get_channel_id_by_name(channel), text)

    def reload_plugin(package_name, class_name):
        """Reload plugin from its plugin class `class_name` from package `package_name`."""
        # obtain the new plugin
        import importlib
        plugin_module = importlib.import_module(package_name) # this will not re-initialize the module, since it's been previously imported
        importlib.reload(plugin_module) # re-initialize the module
        PluginClass = getattr(plugin_module, class_name)

        # replace the old plugin with the new one
        for i, plugin in enumerate(botty.plugins):
            if isinstance(plugin, PluginClass):
                del botty.plugins[i]
                break
        botty.register_plugin(PluginClass(botty))

    def sane():
        """Force the administrator's console into a reasonable default - useful for recovering from weird terminal states."""
        import os
        os.system("stty sane")

    from datetime import datetime
    from plugins.utilities import BasePlugin
    def on_message_default(plugin, message): pass
    def on_message_print(plugin, message):
        """Print out all incoming events - useful for interactive RTM API debugging."""
        if message.get("type") == "message":
            timestamp = datetime.fromtimestamp(int(message["ts"].split(".")[0]))
            channel_name = botty.get_channel_name_by_id(message.get("channel", message.get("previous_message", {}).get("channel")))
            user_name = botty.get_user_name_by_id(message.get("user", message.get("previous_message", {}).get("user")))
            text = message.get("text", message.get("previous_message", {}).get("text"))
            new_text = message.get("message", {}).get("text")
            if new_text:
                print("{timestamp} #{channel} | @{user} {subtype}: {text} -> {new_text}".format(
                    timestamp=timestamp, channel=channel_name, user=user_name,
                    subtype=message.get("subtype", "message"), text=text, new_text=new_text
                ))
            else:
                print("{timestamp} #{channel} | @{user} {subtype}: {text}".format(
                    timestamp=timestamp, channel=channel_name, user=user_name,
                    subtype=message.get("subtype", "message"), text=text
                ))
        elif message.get("type") not in {"ping", "pong", "presence_change", "user_typing", "reconnect_url"}:
            print(message)
    on_message = on_message_default
    class AdHocPlugin(BasePlugin):
        def __init__(self, bot): super().__init__(bot)
        def on_message(self, message): on_message(self, message)
    if not any(isinstance(plugin, AdHocPlugin) for plugin in botty.plugins): # plugin hasn't already been added
        botty.plugins.insert(0, AdHocPlugin(botty)) # the plugin should go before everything else to be able to influence every message

    botty.administrator_console(globals())

botty.start_loop()
