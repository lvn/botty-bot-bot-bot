#!/usr/bin/env python3

import os, re, json
import sqlite3
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--rebuild", help="Completely rebuild the database from the chat history; if not specified, only new chat history is added to the database (slow, but useful if there end up being database issues).", dest="rebuild", action="store_true")
parser.add_argument("--database", help="Path to SQLite database to export chat history to.", required=True)
args = parser.parse_args()

CHAT_HISTORY_DIRECTORY = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "@history")
REBUILD_DATABASE = args.rebuild
SQLITE_DATABASE = args.database

def server_text_to_sendable_text(server_text):
    """Returns `server_text`, a string in Slack server message format, converted into a string in Slack sendable message format."""
    assert isinstance(server_text, str), "`server_text` must be a string rather than \"{}\"".format(server_text)
    text_without_special_sequences = re.sub(r"<[^<>]*>", "", server_text)
    assert "<" not in text_without_special_sequences and ">" not in text_without_special_sequences, "Invalid special sequence in server text \"{}\", perhaps some text needs to be escaped"

    # process link references
    def process_special_sequence(match):
        original, body = match.group(0), match.group(1).split("|")[0]
        if body.startswith("#C"): return original # channel reference, should send unchanged
        if body.startswith("@U"): return original # user reference, should send unchanged
        if body.startswith("!"): return original # special command, should send unchanged
        return body # link, should remove angle brackets and label in order to allow it to linkify
    return re.sub(r"<(.*?)>", process_special_sequence, server_text)

def get_history_files():
    """Returns a mapping from channel IDs to absolute file paths of their history entries"""
    for dirpath, _, filenames in os.walk(CHAT_HISTORY_DIRECTORY):
        result = {}
        for history_file in filenames:
            channel_id, extension = os.path.splitext(os.path.basename(history_file))
            if extension != ".json": continue
            result[channel_id] = os.path.join(dirpath, history_file)
        return result
    return {}

def get_message_text(message):
    """Returns the text value of `message` if it is a valid text message, or `None` otherwise"""
    if message.get("type") != "message": return None
    if not isinstance(message.get("user"), str): return None
    if not isinstance(message.get("text"), str): return None
    if not isinstance(message.get("ts"), str): return None
    return server_text_to_sendable_text(message["text"])

def message_values(channel_id, history_lines, start_at_timestamp_and_timestamp_order, max_channel_offset):
    for entry in history_lines:
        message = json.loads(entry)

        ts = message["ts"].split(".")
        timestamp, timestamp_order = int(ts[0]), int(ts[1])
        if start_at_timestamp_and_timestamp_order and (timestamp, timestamp_order) <= start_at_timestamp_and_timestamp_order: continue

        # ensure the message has text content
        text = get_message_text(message)
        if text is None: continue

        max_channel_offset += 1

        yield (timestamp, timestamp_order, channel_id, message["user"], text, max_channel_offset)

def recreate_database(db_connection):
    db_connection.execute("DROP TABLE IF EXISTS messages")
    db_connection.execute("DROP TABLE IF EXISTS users")
    db_connection.execute("DROP TABLE IF EXISTS channels")
    db_connection.execute("""
    CREATE TABLE messages (
        timestamp INTEGER,
        timestamp_order INTEGER,
        channel_id TEXT,
        user_id TEXT,
        value TEXT,
        channel_offset INTEGER,
        PRIMARY KEY (timestamp, timestamp_order, channel_id),
        FOREIGN KEY (channel_id) REFERENCES channels(channel_id),
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    """)
    db_connection.execute("""
    CREATE TABLE users (
        user_id TEXT PRIMARY KEY,
        user_name TEXT,
        user_real_name TEXT,
        is_bot INTEGER
    )
    """)
    db_connection.execute("""
    CREATE TABLE channels (
        channel_id TEXT PRIMARY KEY,
        channel_name TEXT,
        purpose TEXT
    )
    """)

    # create channel index for messages table
    # we don't need indices for the timestamp and timestamp_order columns since the autoindex covers it
    connection.execute("CREATE INDEX IF NOT EXISTS channel_index ON messages (channel_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS channel_offset_index ON messages (channel_offset)")

def export_metadata(db_connection, users, channels):
    db_connection.execute("DELETE FROM channels")
    db_connection.execute("DELETE FROM users")
    connection.executemany(
        "INSERT INTO users VALUES (?, ?, ?, ?)",
        ((user["id"], user["name"], user["profile"]["real_name"], int(user["is_bot"])) for user in users)
    )
    connection.executemany(
        "INSERT INTO channels VALUES (?, ?, ?)",
        ((channel["id"], channel["name"], channel.get("purpose", {}).get("value")) for channel in channels)
    )

with open(os.path.join(CHAT_HISTORY_DIRECTORY, "metadata", "channels.json")) as f:
    channels = json.load(f)
with open(os.path.join(CHAT_HISTORY_DIRECTORY, "metadata", "users.json")) as f:
    users = json.load(f)

connection = sqlite3.connect(SQLITE_DATABASE)
if REBUILD_DATABASE: recreate_database(connection)

export_metadata(connection, users, channels)

max_channel_offsets = dict(connection.execute("SELECT channel_id, max(channel_offset) FROM messages GROUP BY channel_id").fetchall())

known_channel_ids = {channel["id"] for channel in channels}
for channel_id, history_file in get_history_files().items():
    if channel_id not in known_channel_ids: continue  # ignore deleted channels - channels that we have history for that aren't in the metadata

    # get the latest message in the channel
    result = connection.execute("SELECT timestamp, timestamp_order FROM messages WHERE channel_id = ? ORDER BY timestamp DESC, timestamp_order DESC LIMIT 1", [channel_id]).fetchone()
    if result is None:
        newest_timestamp_and_timestamp_order = None
    else:
        newest_timestamp_and_timestamp_order = result

    max_channel_offset = max_channel_offsets.get(channel_id, -1)

    with open(history_file, "r") as f:
        connection.executemany("INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)", message_values(channel_id, f, newest_timestamp_and_timestamp_order, max_channel_offset))

connection.commit()
connection.close()
