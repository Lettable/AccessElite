from pyrogram import Client, filters
from src import app
from pyrogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    CallbackQuery, 
    Message
)
import asyncio
from pyrogram.enums import ChatMemberStatus, ChatType, ParseMode
import re
import json
from datetime import datetime
from src.database.db import db
from src.utils.invoice import invoice
import config

dmps = {}

REQUIRED_RIGHTS = {
    "can_change_info": True,
    "can_delete_messages": True,
    "can_restrict_members": True,
    "can_invite_users": True,
    "can_pin_messages": True,
    "can_promote_members": True,
    "can_manage_video_chats": True,
    "can_manage_chat": True
}


@app.on_message(filters.command("start"))
async def start(client: Client, message: Message):
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        # Existing group start handler remains the same
        if not await is_group_admin(client, message.chat.id, message.from_user.id):
            await message.reply("Only group admins can configure the bot.")
            return
        
        try:
            bot_member = await client.get_chat_member(message.chat.id, app.me.id)
            if bot_member.status != ChatMemberStatus.ADMINISTRATOR:
                await message.reply("I need to be added as an admin to function properly.")
                return
                
            missing_rights = []
            for right, required in REQUIRED_RIGHTS.items():
                if required and not getattr(bot_member.privileges, right, False):
                    missing_rights.append(right.replace('_', ' '))
            
            if missing_rights:
                await message.reply(
                    f"I'm missing these required admin rights:\n"
                    f"{', '.join(missing_rights)}\n\n"
                    "Please promote me again with all rights.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(
                            "Add me properly", 
                            url=f"https://t.me/{app.me.username}?startgroup=start&admin={'+'.join(REQUIRED_RIGHTS.keys())}"
                        )]
                    ])
                )
                return
                
            await message.reply(
                f"👋 Hello {message.from_user.mention}, thanks for adding me to your group!\n\n"
                "To configure me for this group, please use the /config command.\n\n"
                "I'll help you set up:\n"
                "- Membership pricing\n"
                "- Ads Perm\n"
                "- Refund policy\n"
                "- Payment address\n\n"
                "Once configured, I'll handle paid access automatically!",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            await message.reply(f"Error checking bot status: {str(e)}")
    
    else:
        start_params = message.text.split()
        if len(start_params) > 1 and start_params[1].startswith('-100'):
            group_id = start_params[1]
            
            chat_data = await db.fetch_one(
                "SELECT chat_id, owner_id, mem_pricing, ads_pricing, ltc_address, title FROM chats WHERE chat_id = %s",
                (group_id,))
            
            if not chat_data:
                await message.reply("This group is not configured with the bot yet.")
                return
            
            try:
                chat = await client.get_chat(int(group_id))
                chat_title = chat.title
                owner = await client.get_users(chat_data['owner_id'])
                owner_username = f"@{owner.username}" if owner.username else f"user #{owner.id}"
            except Exception as e:
                chat_title = chat_data.get('title', 'Unknown Group')
                owner_username = f"user #{chat_data['owner_id']}"
            
            keyboard = []
            if chat_data['mem_pricing']:
                keyboard.append([InlineKeyboardButton("Member", callback_data=f"plans_mem_{group_id}")])
            if chat_data['ads_pricing']:
                keyboard.append([InlineKeyboardButton("Ads Perm", callback_data=f"plans_ads_{group_id}")])
            
            if not keyboard:
                await message.reply("This group hasn't set up any pricing plans yet.")
                return
            
            await message.reply(
                f"**Group:** {chat_title}\n"
                f"**Owner:** {owner_username}\n\n"
                "Choose what you want to purchase:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await message.reply(
                f"Welcome to {app.me.first_name}.\nChoose an option below.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Add me to Group", url=f"https://t.me/{app.me.username}?startgroup=start&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages+manage_topics+promote_members+manage_video_chats+manage_chat")],
                    [InlineKeyboardButton("Help", callback_data="show_help"), InlineKeyboardButton("Terms", callback_data="show_terms")]
                ])
            )

@app.on_callback_query(filters.regex(r"^plans_(mem|ads)_(-?\d+)$"))
async def show_plans(client: Client, callback_query: CallbackQuery):
    plan_type = callback_query.matches[0].group(1)
    group_id = callback_query.matches[0].group(2)
    user_id = callback_query.from_user.id
    
    chat_data = await db.fetch_one(
        f"SELECT {plan_type}_pricing, ltc_address FROM chats WHERE chat_id = %s",
        (group_id,))
    
    if not chat_data or not chat_data[f"{plan_type}_pricing"]:
        await callback_query.answer("Owner hasn't set pricing for this yet.", show_alert=True)
        return
    
    try:
        pricing_data = json.loads(chat_data[f"{plan_type}_pricing"])
    except json.JSONDecodeError:
        await callback_query.answer("Invalid pricing data format.", show_alert=True)
        return
    
    keyboard = []
    row = []
    for i, plan in enumerate(pricing_data):
        row.append(InlineKeyboardButton(
            f"{plan['period']}: {plan['price']}$",
            callback_data=f"confirm_{plan_type}_{group_id}_{i}"
        ))
        if len(row) == 2 or i == len(pricing_data) - 1:
            keyboard.append(row)
            row = []
    
    keyboard.append([InlineKeyboardButton("« Back", callback_data=f"back_to_main_{group_id}")])
    
    await callback_query.edit_message_text(
        f"Available {plan_type} plans:\n\n"
        "Select a plan to continue:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^confirm_(mem|ads)_(-?\d+)_(\d+)$"))
async def confirm_plan(client: Client, callback_query: CallbackQuery):
    plan_type = callback_query.matches[0].group(1)
    group_id = callback_query.matches[0].group(2)
    plan_index = int(callback_query.matches[0].group(3))
    user_id = callback_query.from_user.id
    
    chat_data = await db.fetch_one(
        f"SELECT {plan_type}_pricing, ltc_address FROM chats WHERE chat_id = %s",
        (group_id,))
    
    if not chat_data or not chat_data[f"{plan_type}_pricing"]:
        await callback_query.answer("Owner hasn't set pricing for this yet.", show_alert=True)
        return
    
    try:
        pricing_data = json.loads(chat_data[f"{plan_type}_pricing"])
        selected_plan = pricing_data[plan_index]
    except (json.JSONDecodeError, IndexError):
        await callback_query.answer("Invalid pricing data.", show_alert=True)
        return
    
    expiration_date = calculate_expiration(selected_plan['period'])
    
    keyboard = [
        [InlineKeyboardButton("✅ Confirm", callback_data=f"create_invoice_{plan_type}_{group_id}_{plan_index}")],
        [InlineKeyboardButton("« Back to Plans", callback_data=f"plans_{plan_type}_{group_id}")]
    ]
    
    await callback_query.edit_message_text(
        f"**Plan Details:**\n\n"
        f"• Type: {plan_type}\n"
        f"• Period: {selected_plan['period']}\n"
        f"• Price: {selected_plan['price']}$\n"
        f"• Ads Perm: {'Yes' if plan_type == 'ads' else 'No'}\n\n"
        f"If you join today, your access will expire on:\n"
        f"{expiration_date.strftime('%Y-%m-%d %H:%M:%S')}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^create_invoice_(mem|ads)_(-?\d+)_(\d+)$"))
async def create_invoice(client: Client, callback_query: CallbackQuery):
    plan_type = callback_query.matches[0].group(1)
    group_id = callback_query.matches[0].group(2)
    plan_index = int(callback_query.matches[0].group(3))
    user_id = callback_query.from_user.id
    
    # Query database for pricing data
    chat_data = await db.fetch_one(
        f"SELECT {plan_type}_pricing, ltc_address FROM chats WHERE chat_id = %s",
        (group_id,))
    
    if not chat_data or not chat_data[f"{plan_type}_pricing"]:
        await callback_query.answer("Owner hasn't set pricing for this yet.", show_alert=True)
        return
    
    try:
        pricing_data = json.loads(chat_data[f"{plan_type}_pricing"])
        selected_plan = pricing_data[plan_index]
    except (json.JSONDecodeError, IndexError):
        await callback_query.answer("Invalid pricing data.", show_alert=True)
        return
    
    data = {
        "ltc_address": chat_data['ltc_address'],
        "plans": {
            "amount": selected_plan['price']
        }
    }
    
    try:
        result = invoice(config.FF_API_KEY, config.FF_API_SECRET, data)
        
        if result.get('code') != 0:
            raise Exception(result.get('msg', 'Unknown error'))
        
        await db.exec(
            """
            INSERT INTO invoices 
                (user_id, chat_id, token, amount, deposit_address, status, created_at)
            VALUES 
                (%s, %s, %s, %s, %s, 'pending', NOW())
            """,
            (
                user_id,
                group_id,
                result['data']['token'],
                selected_plan['price'],
                result['data']['from']['address']
            )
        )
        
        invoice_id = await db.fetch_val(
            "SELECT LAST_INSERT_ID()"
        )
        
        await callback_query.edit_message_text(
            f"**Invoice Created**\n\n"
            f"• Invoice ID: `{invoice_id}`\n"
            f"• Price: {selected_plan['price']}$\n"
            f"• Payment Address: `{result['data']['from']['address']}`\n"
            f"• Exact Amount to Send: {result['data']['from']['amount']} {result['data']['from']['code']}\n\n"
            f"Please send the exact amount to the address above.\n"
            f"Your access will be granted after confirmation.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back to Group", callback_data=f"back_to_main_{group_id}")]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        print(f"Error creating invoice: {str(e)}")
        
        await callback_query.edit_message_text(
            f"Failed to create invoice: {str(e)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back", callback_data=f"confirm_{plan_type}_{group_id}_{plan_index}")]
            ])
        )
    
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^back_to_main_(-?\d+)$"))
async def back_to_main(client: Client, callback_query: CallbackQuery):
    group_id = callback_query.matches[0].group(1)
    
    chat_data = await db.fetch_one(
        "SELECT chat_id, owner_id, mem_pricing, ads_pricing, ltc_address, title FROM chats WHERE chat_id = %s",
        (group_id,))
    
    if not chat_data:
        await callback_query.answer("Group data not found.", show_alert=True)
        return
    
    try:
        chat = await client.get_chat(int(group_id))
        chat_title = chat.title
        owner = await client.get_users(chat_data['owner_id'])
        owner_username = f"@{owner.username}" if owner.username else f"user #{owner.id}"
    except Exception as e:
        chat_title = chat_data.get('title', 'Unknown Group')
        owner_username = f"user #{chat_data['owner_id']}"
    
    keyboard = []
    if chat_data['mem_pricing']:
        keyboard.append([InlineKeyboardButton("Member", callback_data=f"plans_mem_{group_id}")])
    if chat_data['ads_pricing']:
        keyboard.append([InlineKeyboardButton("Ads Perm", callback_data=f"plans_ads_{group_id}")])
    
    await callback_query.edit_message_text(
        f"**Group:** {chat_title}\n"
        f"**Owner:** {owner_username}\n\n"
        "Choose what you want to purchase:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )
    await callback_query.answer()

def calculate_expiration(period_str):
    from datetime import datetime, timedelta
    
    now = datetime.now()
    parts = period_str.split()
    
    if len(parts) != 2:
        return now + timedelta(days=30)
    
    try:
        num = int(parts[0])
        unit = parts[1].lower()
        
        if 'day' in unit:
            return now + timedelta(days=num)
        elif 'week' in unit:
            return now + timedelta(weeks=num)
        elif 'month' in unit:
            return now + timedelta(days=num*30)
        elif 'year' in unit:
            return now + timedelta(days=num*365)
        else:
            return now + timedelta(days=30)
    except:
        return now + timedelta(days=30)

async def is_group_owner(client: Client, chat_id: int, user_id: int):
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status == ChatMemberStatus.OWNER
    except:
        return False

async def is_group_admin(client: Client, chat_id: int, user_id: int):
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except:
        return False

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

            [InlineKeyboardButton("Back", callback_data="fuck_it_man")]
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
            [InlineKeyboardButton("Back", callback_data="fuck_it_man")]
        ]),
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_callback_query(filters.regex("fuck_it_man"))
async def fuck_it_man(client: Client, callback_query: CallbackQuery):
    await callback_query.message.edit(
        "Welcome back. Choose an option below.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Add me to Group", url=f"https://t.me/{app.me.username}?startgroup=start&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages+manage_topics+promote_members+manage_video_chats+manage_chat")],
            [InlineKeyboardButton("Help", callback_data="show_help"), InlineKeyboardButton("Terms", callback_data="show_terms")]
        ])
    )


@app.on_message(filters.command("config") & filters.group)
async def config_command(client: Client, message: Message):
    chat_id = message.chat.id

    if not await is_group_owner(client, chat_id, message.from_user.id):
        await message.reply("❌ Only the group owner can configure the bot.")
        return

    try:
        bot_member = await client.get_chat_member(chat_id, app.me.id)
        if bot_member.status != ChatMemberStatus.ADMINISTRATOR:
            await message.reply("I need to be added as an admin to function properly.")
            return

        missing_rights = []
        for right, required in REQUIRED_RIGHTS.items():
            if required and not getattr(bot_member.privileges, right, False):
                missing_rights.append(right.replace('_', ' '))

        if missing_rights:
            await message.reply(
                f"I'm missing these required admin rights:\n"
                f"{', '.join(missing_rights)}\n\n"
                "Please promote me again with all rights.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(
                        "Add me properly", 
                        url=f"https://t.me/{app.me.username}?startgroup=start&admin={'+'.join(REQUIRED_RIGHTS.keys())}"
                    )]
                ])
            )
            return

        if chat_id not in dmps:
            dmps[chat_id] = {
                "mem_pricing": [],
                "ads_pricing": [],
                "refundable": True,
                "ltc_address": None,
                "step": "main"
            }

        config_msg = await send_main_config_menu(client, message)

        if config_msg:
            dmps[chat_id]["config_message_id"] = config_msg.id

    except Exception as e:
        await message.reply(f"⚠️ An error occurred while opening the config menu:\n`{e}`", parse_mode=ParseMode.MARKDOWN)


async def send_main_config_menu(client: Client, message: Message):
    chat_id = message.chat.id
    config = dmps.get(chat_id, {})
    
    text = (
        "⚙️ **Group Configuration** ⚙️\n\n"
        f"Configuring: {message.chat.title}\n\n"
        "Current settings:\n"
        f"• **Membership Pricing:** {'Set' if config.get('mem_pricing') else 'Not set'}\n"
        f"• **Ads Perm:** {'Set' if config.get('ads_pricing') else 'Not set'}\n"
        f"• **Refund Policy:** {'✅ Enabled' if config.get('refundable', True) else '❌ Disabled'}\n"
        f"• **LTC Address:** {'✅ Set' if config.get('ltc_address') else '❌ Not set'}\n\n"
        "Select an option to configure:"
    )
    
    buttons = [
        [InlineKeyboardButton("Membership Pricing", callback_data=f"config_mem_pricing:{chat_id}")],
        [InlineKeyboardButton("Ads Perm", callback_data=f"config_ads_pricing:{chat_id}")],
        [InlineKeyboardButton("Refund Policy", callback_data=f"config_refund:{chat_id}")],
        [InlineKeyboardButton("Set LTC Address", callback_data=f"config_ltc_address:{chat_id}")],
        [InlineKeyboardButton("✅ Confirm Configuration", callback_data=f"config_confirm:{chat_id}")]
    ]
    
    return await message.reply(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.MARKDOWN
    )

async def show_main_config_menu(client: Client, message: Message):
    chat_id = message.chat.id
    config = dmps.get(chat_id, {})
    
    text = (
        "⚙️ **Group Configuration** ⚙️\n\n"
        f"Configuring: {message.chat.title}\n\n"
        "Current settings:\n"
        f"• **Membership Pricing:** {'Set' if config.get('mem_pricing') else 'Not set'}\n"
        f"• **Ads Perm:** {'Set' if config.get('ads_pricing') else 'Not set'}\n"
        f"• **Refund Policy:** {'✅ Enabled' if config.get('refundable', True) else '❌ Disabled'}\n"
        f"• **LTC Address:** {'✅ Set' if config.get('ltc_address') else '❌ Not set'}\n\n"
        "Select an option to configure:"
    )
    
    buttons = [
        [InlineKeyboardButton("Membership Pricing", callback_data=f"config_mem_pricing:{chat_id}")],
        [InlineKeyboardButton("Ads Perm", callback_data=f"config_ads_pricing:{chat_id}")],
        [InlineKeyboardButton("Refund Policy", callback_data=f"config_refund:{chat_id}")],
        [InlineKeyboardButton("Set LTC Address", callback_data=f"config_ltc_address:{chat_id}")],
        [InlineKeyboardButton("✅ Confirm Configuration", callback_data=f"config_confirm:{chat_id}")]
    ]
    
    if "config_message_id" in config:
        try:
            await client.edit_message_text(
                chat_id=chat_id,
                message_id=config["config_message_id"],
                text=text,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        except:
            pass
    
    new_msg = await message.reply(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.MARKDOWN
    )

    dmps[chat_id]["config_message_id"] = new_msg.id

@app.on_callback_query(filters.regex(r"^config_ltc_address:(\-?\d+)$"))
async def config_ltc_callback(client: Client, callback_query: CallbackQuery):
    chat_id = int(callback_query.data.split(":")[1])
    
    if not await is_group_owner(client, chat_id, callback_query.from_user.id):
        await callback_query.answer("Only admins can configure this group.", show_alert=True)
        return
    
    dmps[chat_id]["step"] = "set_ltc_address"
    
    await callback_query.message.edit(
        "💰 **Set Litecoin Address** 💰\n\n"
        "Please send your Litecoin (LTC) address where you want to receive payments.\n\n"
        "Example: `LbFz5YdzhF4YkMPe6ZJ9mRzY6vE8XgJX7q`\n\n"
        "⚠️ Make sure this address is correct as all payments will be sent here. Click back after sending!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ Back", callback_data=f"back_to_main_config:{chat_id}")]
        ]),
        parse_mode=ParseMode.MARKDOWN
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^config_(mem|ads)_pricing:(\-?\d+)$"))
async def config_pricing_callback(client: Client, callback_query: CallbackQuery):
    data_parts = callback_query.data.split(":")
    pricing_type = data_parts[0].split("_")[1]
    chat_id = int(data_parts[1])
    
    if not await is_group_owner(client, chat_id, callback_query.from_user.id):
        await callback_query.answer("Only admins can configure this group.", show_alert=True)
        return
    
    await show_pricing_menu(client, callback_query, pricing_type, chat_id)

@app.on_callback_query(filters.regex(r"^config_refund:(\-?\d+)$"))
async def config_refund_callback(client: Client, callback_query: CallbackQuery):
    chat_id = int(callback_query.data.split(":")[1])
    
    if not await is_group_owner(client, chat_id, callback_query.from_user.id):
        await callback_query.answer("Only admins can configure this group.", show_alert=True)
        return
    
    await show_refund_menu(client, callback_query, chat_id)

@app.on_callback_query(filters.regex(r"^config_confirm:(\-?\d+)$"))
async def config_confirm_callback(client: Client, callback_query: CallbackQuery):
    chat_id = int(callback_query.data.split(":")[1])
    
    if not await is_group_owner(client, chat_id, callback_query.from_user.id):
        await callback_query.answer("Only admins can configure this group.", show_alert=True)
        return
    
    await confirm_configuration(client, callback_query, chat_id)

async def show_pricing_menu(client: Client, message_or_callback: Message | CallbackQuery, pricing_type: str, chat_id: int):
    config = dmps.get(chat_id, {})
    pricing = config.get(f"{pricing_type}_pricing", [])
    
    pricing_text = "\n".join([f"{item['period']}: {item['price']}$" for item in pricing]) if pricing else "No pricing set"
    
    text = (
        f"💰 **{'Membership' if pricing_type == 'mem' else 'Admin'} Pricing** 💰\n\n"
        f"Current pricing:\n{pricing_text}\n\n"
        "Choose an action:"
    )
    
    if isinstance(message_or_callback, CallbackQuery):
        chat_title = message_or_callback.message.chat.title
        text = text.replace("Current pricing:", f"Current pricing for {chat_title}:")
        await message_or_callback.message.edit(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Replace Pricing", callback_data=f"pricing_{pricing_type}_replace:{chat_id}")],
                [InlineKeyboardButton("Append Pricing", callback_data=f"pricing_{pricing_type}_append:{chat_id}")],
                [InlineKeyboardButton("Clear Pricing", callback_data=f"pricing_{pricing_type}_clear:{chat_id}")],
                [InlineKeyboardButton("↩️ Back", callback_data=f"back_to_main_config:{chat_id}")]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )
        await message_or_callback.answer()
    else:
        chat_title = message_or_callback.chat.title
        text = text.replace("Current pricing:", f"Current pricing for {chat_title}:")
        await message_or_callback.reply(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Replace Pricing", callback_data=f"pricing_{pricing_type}_replace:{chat_id}")],
                [InlineKeyboardButton("Append Pricing", callback_data=f"pricing_{pricing_type}_append:{chat_id}")],
                [InlineKeyboardButton("Clear Pricing", callback_data=f"pricing_{pricing_type}_clear:{chat_id}")],
                [InlineKeyboardButton("↩️ Back", callback_data=f"back_to_main_config:{chat_id}")]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )

async def show_refund_menu(client: Client, callback_query: CallbackQuery, chat_id: int):
    config = dmps.get(chat_id, {})
    
    text = (
        "🔙 **Refund Policy** 🔙\n\n"
        f"Setting for {callback_query.message.chat.title}\n\n"
        "Do you want to allow refunds for your group?\n\n"
        f"Current setting: {'✅ Enabled' if config.get('refundable', True) else '❌ Disabled'}"
    )
    
    await callback_query.message.edit(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes", callback_data=f"refund_yes:{chat_id}"),
             InlineKeyboardButton("❌ No", callback_data=f"refund_no:{chat_id}")],
            [InlineKeyboardButton("↩️ Back", callback_data=f"back_to_main_config:{chat_id}")]
        ]),
        parse_mode=ParseMode.MARKDOWN
    )
    await callback_query.answer()

async def confirm_configuration(client: Client, callback_query: CallbackQuery, chat_id: int):
    config = dmps.get(chat_id, {})
    
    if not config.get("mem_pricing"):
        await callback_query.answer("Please set membership pricing first!", show_alert=True)
        return
    if not config.get("ads_pricing"):
        await callback_query.answer("Please set Ads Perm first!", show_alert=True)
        return
    if not config.get("ltc_address"):
        await callback_query.answer("Please set your LTC address first!", show_alert=True)
        return
    
    try:
        await save_chat_config(
            chat_id=chat_id,
            owner_id=callback_query.from_user.id,
            mem_pricing=config["mem_pricing"],
            ads_pricing=config["ads_pricing"],
            refundable=config["refundable"],
            ltc_address=config["ltc_address"]
        )
        
        text = (
            f"✅ **{callback_query.message.chat.title} is now fully configured.**\n\n"
            "From this point on, **we handle everything** — access, admin roles, and link control.\n\n"
            "🔒 **Never share your group’s invite link directly.** Instead, use this secure gateway link:\n"
            f"`https://t.me/{app.me.username}?start={callback_query.message.chat.id}`\n\n"
            "🚫 Do **NOT** add admins manually. Anyone with invite rights can leak your setup. Trust the system — we’ve got your back.\n\n"
            "**You're good to go. Let us manage the gates.**"
        )

        await callback_query.message.edit(
            text,
            parse_mode=ParseMode.MARKDOWN
        )
        
        if chat_id in dmps:
            del dmps[chat_id]
            
    except Exception as e:
        await callback_query.message.edit(
            f"❌ **Error saving configuration:** {str(e)}\n\n"
            "Please try again or contact support.",
            parse_mode=ParseMode.MARKDOWN
        )

@app.on_callback_query(filters.regex(r"^pricing_(mem|ads)_(replace|append|clear):(\-?\d+)$"))
async def pricing_action_callback(client: Client, callback_query: CallbackQuery):
    data_parts = callback_query.data.split(":")
    action_parts = data_parts[0].split("_")
    pricing_type = action_parts[1]
    action = action_parts[2]
    chat_id = int(data_parts[1])
    
    if not await is_group_owner(client, chat_id, callback_query.from_user.id):
        await callback_query.answer("Only admins can configure this group.", show_alert=True)
        return
    
    config = dmps.get(chat_id, {})
    
    if action == "clear":
        config[f"{pricing_type}_pricing"] = []
        await callback_query.answer("Pricing cleared!")
        await show_pricing_menu(client, callback_query, pricing_type, chat_id)
        return
    
    config["step"] = f"pricing_{pricing_type}_{action}"
    dmps[chat_id] = config
    
    if action == "replace":
        text = (
            "🔄 **Replace Pricing**\n\n"
            "Please send the new pricing in this exact format:\n\n"
            "`1 week: 20$\n"
            "2 weeks: 25$\n"
            "1 month: 50$`\n\n"
            "**Allowed time units:** day, days, week, weeks, month, months, year, years\n"
            "**Price format:** Must end with $ sign\n\n"
            "Example:\n"
            "`3 days: 5$\n"
            "2 weeks: 15$\n"
            "1 month: 30$`"
        )
    elif action == "append":
        text = (
            "➕ **Append Pricing**\n\n"
            "Please send additional pricing in this exact format:\n\n"
            "`3 week: 40$\n"
            "4 weeks: 45$\n"
            "1 month: 48$`\n\n"
            "This will be added to your existing pricing.\n\n"
            "**Allowed time units:** day, days, week, weeks, month, months, year, years\n"
            "**Price format:** Must end with $ sign"
        )
    
    await callback_query.message.edit(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ Back", callback_data=f"back_to_main_config:{chat_id}")]
        ]),
        parse_mode=ParseMode.MARKDOWN
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^refund_(yes|no):(\-?\d+)$"))
async def refund_policy_callback(client: Client, callback_query: CallbackQuery):
    data_parts = callback_query.data.split(":")
    policy = data_parts[0].split("_")[1]
    chat_id = int(data_parts[1])
    
    if not await is_group_owner(client, chat_id, callback_query.from_user.id):
        await callback_query.answer("Only admins can configure this group.", show_alert=True)
        return
    
    dmps[chat_id]["refundable"] = (policy == "yes")
    await show_main_config_menu(client, callback_query.message)
    await callback_query.answer("Refund policy updated!")

@app.on_callback_query(filters.regex(r"^back_to_main_config:(\-?\d+)$"))
async def back_to_main_config_callback(client: Client, callback_query: CallbackQuery):
    chat_id = int(callback_query.data.split(":")[1])
    
    if not await is_group_owner(client, chat_id, callback_query.from_user.id):
        await callback_query.answer("Only the group owner can configure this.", show_alert=True)
        return
    
    config = dmps.get(chat_id, {})
    if "config_message_id" not in config:
        await callback_query.answer("Session expired. Please use /config again.", show_alert=True)
        return
    
    try:
        text = (
            "⚙️ **Group Configuration** ⚙️\n\n"
            f"Configuring: {callback_query.message.chat.title}\n\n"
            "Current settings:\n"
            f"• **Membership Pricing:** {'Set' if config.get('mem_pricing') else 'Not set'}\n"
            f"• **Ads Perm:** {'Set' if config.get('ads_pricing') else 'Not set'}\n"
            f"• **Refund Policy:** {'✅ Enabled' if config.get('refundable', True) else '❌ Disabled'}\n"
            f"• **LTC Address:** {'✅ Set' if config.get('ltc_address') else '❌ Not set'}\n\n"
            "Select an option to configure:"
        )
        
        buttons = [
            [InlineKeyboardButton("Membership Pricing", callback_data=f"config_mem_pricing:{chat_id}")],
            [InlineKeyboardButton("Ads Perm", callback_data=f"config_ads_pricing:{chat_id}")],
            [InlineKeyboardButton("Refund Policy", callback_data=f"config_refund:{chat_id}")],
            [InlineKeyboardButton("Set LTC Address", callback_data=f"config_ltc_address:{chat_id}")],
            [InlineKeyboardButton("✅ Confirm Configuration", callback_data=f"config_confirm:{chat_id}")]
        ]
        
        await callback_query.message.edit(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN
        )
        await callback_query.answer()
    except Exception as e:
        await callback_query.answer("Failed to update menu. Please use /config again.", show_alert=True)

@app.on_message(filters.group & filters.text)
async def handle_config_input(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if chat_id not in dmps:
        return
    
    config = dmps[chat_id]
    step = config.get("step", "")

    if step == "set_ltc_address":
        ltc_address = message.text.strip()
        
        if not (ltc_address.startswith('L') or ltc_address.startswith('M')) or len(ltc_address) < 26 or len(ltc_address) > 35:
            error_msg = await message.reply(
                "❌ Invalid Litecoin address format.\n"
                "A valid LTC address should start with **L** or **M** and be 26–35 characters long.\n"
                "Please try again.",
                parse_mode=ParseMode.MARKDOWN
            )
            await asyncio.sleep(10)
            try:
                await error_msg.delete()
                await message.delete()
            except:
                pass
            return

        config["ltc_address"] = ltc_address
        config["step"] = "main"

        try:
            await message.delete()
        except:
            pass

        await show_main_config_menu(client, message)
        return

    if not step.startswith("pricing_"):
        return

    if not await is_group_owner(client, chat_id, user_id):
        await message.reply("Only admins can configure this group.")
        return

    _, pricing_type, action = step.split("_")
    
    try:
        pricing_items = parse_pricing_input(message.text)

        if action == "replace":
            config[f"{pricing_type}_pricing"] = pricing_items
        elif action == "append":
            config[f"{pricing_type}_pricing"].extend(pricing_items)

        config["step"] = "main"

        try:
            await message.delete()
        except:
            pass

        await show_pricing_menu(client, message, pricing_type, chat_id)

    except ValueError as e:
        error_msg = await message.reply(
            f"❌ Invalid pricing format: {str(e)}\n\n"
            "Use this format (each entry on a new line):\n"
            "`1 week: 20$\n"
            "2 weeks: 25$`",
            parse_mode=ParseMode.MARKDOWN
        )

        await asyncio.sleep(10)
        try:
            await error_msg.delete()
            await message.delete()
        except:
            pass


def parse_pricing_input(text: str) -> list:
    """Parse pricing input into a list of dicts with period and price"""
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    pricing_items = []
    
    for line in lines:
        match = re.match(r'^(\d+)\s+(day|days|week|weeks|month|months|year|years)\s*:\s*(\d+)\s*\$$', line, re.IGNORECASE)
        if not match:
            raise ValueError(f"Invalid line format: '{line}'")
        
        quantity, unit, price = match.groups()
        period = f"{quantity} {unit}"
        pricing_items.append({
            "period": period.lower(),
            "price": int(price)
        })
    
    return pricing_items

def format_pricing(pricing):
    return "\n".join([f"- {item['period']}: {item['price']}$" for item in pricing]) if pricing else "No pricing set"

async def save_chat_config(chat_id, owner_id, mem_pricing, ads_pricing, refundable, ltc_address):
    print('Saving data:', chat_id, owner_id, mem_pricing, ads_pricing, refundable, ltc_address)
    
    await db.exec(
        """
        INSERT INTO chats (chat_id, owner_id, mem_pricing, ads_pricing, refundable, ltc_address, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE
            mem_pricing = VALUES(mem_pricing),
            ads_pricing = VALUES(ads_pricing),
            refundable = VALUES(refundable),
            ltc_address = VALUES(ltc_address),
            updated_at = NOW()
        """,
        (
            chat_id,
            owner_id,
            json.dumps(mem_pricing),
            json.dumps(ads_pricing),
            refundable,
            ltc_address
        )
    )
