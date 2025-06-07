
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from src import app
from pyrogram.enums import ParseMode

@app.on_message(filters.command("start"))
async def start(client: Client, message: Message):
    await message.reply(
        f"Welcome to {app.me.first_name}.\nChoose an option below.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Add me to Group", url=f"https://t.me/{app.me.username}?startgroup=start&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages+manage_topics+promote_members+manage_video_chats+manage_chat")],
            [InlineKeyboardButton("Help", callback_data="show_help"), InlineKeyboardButton("Terms", callback_data="show_terms")]
        ])
    )

@app.on_callback_query(filters.regex("show_help"))
async def show_help(client: Client, callback_query: CallbackQuery):
    await callback_query.message.edit(
        "📜 **Help & Overview** 📜\n\n"
        "This bot automates paid access to private Telegram groups. Key features include:\n\n"
        "- Secure, subscription-based entry system\n"
        "- Auto-generated invite links after payment\n"
        "- Role assignment (Member/Admin) based on plan\n"
        "- Real-time membership verification\n"
        "- Notifies users before their subscription expires\n"
        "- Complete hands-off income system for group owners\n\n"
        "Earn passive income while the bot handles access, billing, and user management.",
        reply_markup=InlineKeyboardMarkup([
            
            [InlineKeyboardButton("Back", callback_data="back_to_main")]
        ]),
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_callback_query(filters.regex("show_terms"))
async def show_terms(client: Client, callback_query: CallbackQuery):
    text = (
        "📜 **Terms of Use** 📜\n\n"
        "- Refunds are only available **if the group owner explicitly allows them**.\n"
        "- The bot is **not responsible** for scams, frauds, or misleading groups.\n"
        "- Always verify the group's legitimacy and wallet address **before joining**.\n"
        "- By proceeding, you **agree to these terms** and accept full responsibility for your actions."
    )
    await callback_query.message.edit(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Back", callback_data="back_to_main")]
        ]),
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_callback_query(filters.regex("back_to_main"))
async def back_to_main(client: Client, callback_query: CallbackQuery):
    await callback_query.message.edit(
        "Welcome back. Choose an option below.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Add me to Group", url=f"https://t.me/{app.me.username}?startgroup=start&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages+manage_topics+promote_members+manage_video_chats+manage_chat")],
            [InlineKeyboardButton("Help", callback_data="show_help"), InlineKeyboardButton("Terms", callback_data="show_terms")]
        ])
    )

