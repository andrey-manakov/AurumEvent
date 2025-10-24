"""Tomorrow Planner Telegram bot."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, Optional

from dotenv import load_dotenv
import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException

from db import Database, load_database

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_PATH = os.getenv("DATABASE_PATH")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Set it in the .env file.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
db: Database = load_database(DATABASE_PATH)

BOT_USERNAME: Optional[str] = None
DEFAULT_TIME_TEXT = "Tomorrow 19:00"


@dataclass
class EventCreationState:
    """Holds conversation state for /new command."""

    step_index: int = 0
    data: Dict[str, str] = field(default_factory=dict)

    steps = ("title", "location", "type", "time")

    @property
    def current_step(self) -> str:
        return self.steps[self.step_index]

    def advance(self) -> None:
        self.step_index += 1

    def is_complete(self) -> bool:
        return self.step_index >= len(self.steps)


user_states: Dict[int, EventCreationState] = {}


def escape_html(text: Optional[str]) -> str:
    safe_text = text or ""
    return (
        safe_text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def ensure_bot_username() -> str:
    global BOT_USERNAME
    if BOT_USERNAME:
        return BOT_USERNAME
    info = bot.get_me()
    BOT_USERNAME = info.username or ""
    return BOT_USERNAME


def get_invite_link(event_id: int) -> str:
    username = ensure_bot_username()
    return f"https://t.me/{username}?start=join_{event_id}"


def build_rsvp_markup(event_id: int) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    buttons = [
        ("✅ Yes", "yes"),
        ("❌ No", "no"),
        ("❔ Maybe", "maybe"),
    ]
    markup.row(
        *[
            types.InlineKeyboardButton(text, callback_data=f"rsvp:{event_id}:{status}")
            for text, status in buttons
        ]
    )
    return markup


def build_event_text(
    event: Dict[str, str],
    user_status: Optional[str] = None,
    counts: Optional[Dict[str, int]] = None,
    include_invite: bool = False,
    show_status: bool = True,
) -> str:
    lines = [
        f"📌 <b>{escape_html(str(event['title']))}</b>",
        f"Type: {escape_html(str(event['type']))}",
        f"Time: {escape_html(str(event['time']))}",
        f"Location: {escape_html(str(event['location']))}",
    ]
    if counts is not None:
        lines.append(
            "RSVPs — Yes: {yes} | No: {no} | Maybe: {maybe}".format(
                yes=counts.get("yes", 0),
                no=counts.get("no", 0),
                maybe=counts.get("maybe", 0),
            )
        )
    if show_status:
        status_text = "Not set" if not user_status else user_status.title()
        lines.append(f"Your RSVP: {status_text}")
    if include_invite:
        lines.append(f"Invite friends ➜ {escape_html(get_invite_link(event['id']))}")
    return "\n".join(lines)


def prompt_for_step(chat_id: int, step: str) -> None:
    if step == "title":
        bot.send_message(
            chat_id,
            "Let's plan tomorrow! What's the event name or short description?\n\nSend /cancel to stop anytime.",
        )
    elif step == "location":
        bot.send_message(
            chat_id,
            "Where will it happen? Send a location pin or type the place.",
        )
    elif step == "type":
        bot.send_message(
            chat_id,
            "What type of event is it? (e.g., dinner, movie, walk)",
        )
    elif step == "time":
        bot.send_message(
            chat_id,
            f"What time tomorrow? Use 24-hour format like 19:00. Leave empty for {DEFAULT_TIME_TEXT}.",
        )


def reset_state(user_id: int) -> None:
    user_states.pop(user_id, None)


def user_has_access(event_row: Dict[str, str], user_id: int) -> bool:
    if event_row["user_id"] == user_id:
        return True
    return db.get_rsvp(event_row["id"], user_id) is not None


def handle_join_event(message: types.Message, event_id: int) -> None:
    if message.chat.type != "private":
        bot.reply_to(message, "Please message me privately to join this event.")
        return

    event = db.get_event(event_id)
    if not event:
        bot.reply_to(message, "Event not found or already deleted.")
        return

    user_id = message.from_user.id
    rsvp_row = db.get_rsvp(event_id, user_id)
    status = rsvp_row["status"] if rsvp_row else "maybe"
    if not rsvp_row:
        db.upsert_rsvp(event_id, user_id, status)

    counts = db.get_rsvp_counts(event_id)
    text = "You're invited to an event for tomorrow!\n\n" + build_event_text(
        event,
        user_status=status,
        counts=counts,
    )
    bot.send_message(
        message.chat.id,
        text,
        reply_markup=build_rsvp_markup(event_id),
    )


def finish_event_creation(user_id: int, chat_id: int, state: EventCreationState) -> None:
    event_id = db.create_event(
        user_id=user_id,
        title=state.data["title"],
        event_type=state.data["type"],
        time=state.data["time"],
        location=state.data["location"],
    )
    reset_state(user_id)
    event = db.get_event(event_id)
    counts = db.get_rsvp_counts(event_id)
    message_text = "Event saved! Share it with friends.\n\n" + build_event_text(
        event,
        user_status=None,
        counts=counts,
        include_invite=True,
    )
    bot.send_message(chat_id, message_text, reply_markup=build_rsvp_markup(event_id))


@bot.message_handler(commands=["start"])
def handle_start(message: types.Message) -> None:
    parts = message.text.split()
    if len(parts) > 1 and parts[1].startswith("join_"):
        try:
            event_id = int(parts[1].split("_", maxsplit=1)[1])
        except (IndexError, ValueError):
            bot.reply_to(message, "Invalid invitation link.")
            return
        handle_join_event(message, event_id)
        return

    bot.send_message(
        message.chat.id,
        "Hi! I'm Tomorrow Planner. Use /new to create an event for tomorrow or /help for all commands.",
    )


@bot.message_handler(commands=["help"])
def handle_help(message: types.Message) -> None:
    bot.send_message(
        message.chat.id,
        "Commands:\n/new – create an event for tomorrow\n/my – manage events you created\n/help – show this help message",
    )


@bot.message_handler(commands=["new"])
def handle_new(message: types.Message) -> None:
    if message.chat.type != "private":
        bot.reply_to(message, "Please start a private chat with me to create events.")
        return

    user_states[message.from_user.id] = EventCreationState()
    prompt_for_step(message.chat.id, "title")


@bot.message_handler(commands=["cancel"])
def handle_cancel(message: types.Message) -> None:
    if message.from_user.id in user_states:
        reset_state(message.from_user.id)
        bot.reply_to(message, "Event creation cancelled.")
    else:
        bot.reply_to(message, "Nothing to cancel.")


@bot.message_handler(commands=["my"])
def handle_my(message: types.Message) -> None:
    if message.chat.type != "private":
        bot.reply_to(message, "Please open a private chat to view your events.")
        return

    events = db.get_events_by_user(message.from_user.id)
    if not events:
        bot.send_message(message.chat.id, "You haven't created any events yet. Use /new to start.")
        return

    for event in events:
        summary = f"<b>{escape_html(str(event['title']))}</b> — {escape_html(str(event['time']))} ({escape_html(str(event['type']))})"
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("View", callback_data=f"view:{event['id']}")
        )
        markup.row(
            types.InlineKeyboardButton("Delete", callback_data=f"delete:{event['id']}")
        )
        bot.send_message(message.chat.id, summary, reply_markup=markup)


@bot.message_handler(func=lambda msg: msg.from_user.id in user_states, content_types=["text", "location"])
def handle_event_creation(message: types.Message) -> None:
    state = user_states[message.from_user.id]
    step = state.current_step

    if step == "title":
        if not message.text or not message.text.strip():
            bot.reply_to(message, "Please send a short title or description for the event.")
            return
        state.data["title"] = message.text.strip()
        state.advance()
        prompt_for_step(message.chat.id, state.current_step)
        return

    if step == "location":
        if message.content_type == "location" and message.location:
            lat = message.location.latitude
            lon = message.location.longitude
            state.data["location"] = f"Pin: {lat:.6f}, {lon:.6f}"
        elif message.text and message.text.strip():
            state.data["location"] = message.text.strip()
        else:
            bot.reply_to(message, "Send a location pin or type the location.")
            return
        state.advance()
        prompt_for_step(message.chat.id, state.current_step)
        return

    if step == "type":
        if not message.text or not message.text.strip():
            bot.reply_to(message, "Please tell me the event type (e.g., dinner, movie, walk).")
            return
        state.data["type"] = message.text.strip()
        state.advance()
        prompt_for_step(message.chat.id, state.current_step)
        return

    if step == "time":
        if message.content_type != "text":
            bot.reply_to(message, "Please type the time, for example 19:30.")
            return
        user_text = message.text.strip() if message.text else ""
        if not user_text:
            time_value = DEFAULT_TIME_TEXT
        elif len(user_text) == 5 and user_text[2] == ":" and user_text.replace(":", "").isdigit():
            time_value = f"Tomorrow {user_text}"
        else:
            time_value = user_text
        state.data["time"] = time_value
        finish_event_creation(message.from_user.id, message.chat.id, state)


def handle_view_callback(call: types.CallbackQuery, event_id: int) -> None:
    event = db.get_event(event_id)
    if not event:
        bot.answer_callback_query(call.id, "Event not found.", show_alert=True)
        return

    if not user_has_access(event, call.from_user.id):
        bot.answer_callback_query(call.id, "You do not have access to this event.", show_alert=True)
        return

    counts = db.get_rsvp_counts(event_id)
    rsvp_row = db.get_rsvp(event_id, call.from_user.id)
    text = build_event_text(
        event,
        user_status=rsvp_row["status"] if rsvp_row else None,
        counts=counts,
        include_invite=event["user_id"] == call.from_user.id,
    )
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, text, reply_markup=build_rsvp_markup(event_id))


def handle_delete_callback(call: types.CallbackQuery, event_id: int) -> None:
    event = db.get_event(event_id)
    if not event or event["user_id"] != call.from_user.id:
        bot.answer_callback_query(call.id, "You can only delete your own events.", show_alert=True)
        return

    deleted = db.delete_event(event_id, call.from_user.id)
    if deleted:
        bot.answer_callback_query(call.id, "Event deleted.")
        try:
            bot.edit_message_text("Event deleted.", call.message.chat.id, call.message.message_id)
        except ApiTelegramException:
            bot.send_message(call.message.chat.id, "Event deleted.")
    else:
        bot.answer_callback_query(call.id, "Event not found.", show_alert=True)


def handle_rsvp_callback(call: types.CallbackQuery, event_id: int, status: str) -> None:
    if status not in {"yes", "no", "maybe"}:
        bot.answer_callback_query(call.id, "Unknown option.", show_alert=True)
        return

    event = db.get_event(event_id)
    if not event:
        bot.answer_callback_query(call.id, "Event not found.", show_alert=True)
        return

    if not user_has_access(event, call.from_user.id):
        bot.answer_callback_query(call.id, "Join via the invite link first.", show_alert=True)
        return

    db.upsert_rsvp(event_id, call.from_user.id, status)
    counts = db.get_rsvp_counts(event_id)
    text = build_event_text(
        event,
        user_status=status,
        counts=counts,
        include_invite=event["user_id"] == call.from_user.id,
    )
    try:
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=build_rsvp_markup(event_id),
        )
    except ApiTelegramException:
        bot.send_message(call.message.chat.id, text, reply_markup=build_rsvp_markup(event_id))
    bot.answer_callback_query(call.id, f"RSVP set to {status.title()}.")


@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call: types.CallbackQuery) -> None:
    if call.data.startswith("view:"):
        try:
            event_id = int(call.data.split(":", maxsplit=1)[1])
        except ValueError:
            bot.answer_callback_query(call.id, "Invalid event id.", show_alert=True)
            return
        handle_view_callback(call, event_id)
    elif call.data.startswith("delete:"):
        try:
            event_id = int(call.data.split(":", maxsplit=1)[1])
        except ValueError:
            bot.answer_callback_query(call.id, "Invalid event id.", show_alert=True)
            return
        handle_delete_callback(call, event_id)
    elif call.data.startswith("rsvp:"):
        parts = call.data.split(":")
        if len(parts) != 3:
            bot.answer_callback_query(call.id, "Invalid RSVP data.", show_alert=True)
            return
        try:
            event_id = int(parts[1])
        except ValueError:
            bot.answer_callback_query(call.id, "Invalid RSVP data.", show_alert=True)
            return
        handle_rsvp_callback(call, event_id, parts[2])
    else:
        bot.answer_callback_query(call.id)


def main() -> None:
    logging.info("Tomorrow Planner bot started")
    bot.infinity_polling(skip_pending=True)


if __name__ == "__main__":
    main()
