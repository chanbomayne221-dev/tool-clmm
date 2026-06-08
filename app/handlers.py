"""python-telegram-bot handlers."""
import asyncio
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)

from .config import ADMIN_IDS, BOT_TOKEN
from .database import db
from .menu import (
    main_menu, admin_menu, auto_control_menu,
    BTN_PREDICT, BTN_STATS, BTN_HELP, BTN_ADMIN,
    BTN_ADMIN_AUTO, BTN_ADMIN_SOURCE, BTN_ADMIN_BAN, BTN_ADMIN_USERS,
    BTN_ADMIN_BROADCAST, BTN_ADMIN_SETTINGS, BTN_BACK,
    BTN_AUTO_RUN, BTN_AUTO_STOP, BTN_AUTO_CHANGE,
)
from .prediction_service import build_next_prediction_message
from .telethon_client import verify_source, set_source, get_source, _normalize_input

log = logging.getLogger(__name__)

# Conversation state per user
PENDING = {}  # user_id -> state string


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


async def _track_and_check(update: Update) -> bool:
    u = update.effective_user
    if not u:
        return False
    await db.upsert_user(u.id, u.username or "", u.first_name or "")
    if await db.is_banned(u.id):
        try:
            await update.effective_message.reply_text("⛔ Bạn đã bị khóa khỏi bot")
        except Exception:
            pass
        return False
    return True


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _track_and_check(update):
        return
    uid = update.effective_user.id
    await update.message.reply_text(
        "👋 Chào mừng đến *Tài Xỉu Prediction Bot*\n\nDùng menu bên dưới để bắt đầu.",
        parse_mode="Markdown",
        reply_markup=main_menu(uid),
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _track_and_check(update):
        return
    await update.message.reply_text(
        "🆘 *Hỗ trợ*\n\n"
        "• Bấm 📊 để xem dự đoán phiên hiện tại\n"
        "• Bấm 📈 để xem thống kê thắng/thua\n"
        "• Admin có menu riêng để cấu hình bot",
        parse_mode="Markdown",
        reply_markup=main_menu(update.effective_user.id),
    )


async def on_predict(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    res = await build_next_prediction_message(refresh_from_source=True)
    if not res:
        await update.message.reply_text(
            "⏳ Không lấy được dữ liệu từ room nguồn.\n\n"
            "Admin hãy vào 👑 Admin → 📡 Nhóm check LS để đặt room nguồn."
        )
        return
    _, msg, _, _ = res
    await update.message.reply_text(msg)


async def on_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stats = await db.prediction_stats()
    total_sessions = len(await db.recent_sessions(limit=100000))
    total = stats["total"]
    wins = stats["wins"]
    losses = stats["losses"]
    acc = (wins / total * 100) if total else 0
    text = (
        "📈 *Thống kê*\n\n"
        f"🎲 Số phiên thu thập: *{total_sessions}*\n"
        f"🎯 Tổng dự đoán đã chấm: *{total}*\n"
        f"✅ Thắng: *{wins}*\n"
        f"❌ Thua: *{losses}*\n"
        f"📊 Tỉ lệ: *{acc:.1f}%*"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def on_admin_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("❌ Bạn không có quyền.")
        return
    await update.message.reply_text(
        "👑 *Admin menu*", parse_mode="Markdown", reply_markup=admin_menu()
    )


async def on_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    PENDING.pop(uid, None)
    await update.message.reply_text("⬅️ Quay lại menu chính", reply_markup=main_menu(uid))


# ---------- 📡 Nhóm check LS ----------

async def on_admin_source(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    current = await get_source()
    PENDING[uid] = "await_source"
    await update.message.reply_text(
        "📌 Gửi *link / username / ID* nhóm dùng để check lịch sử phiên.\n\n"
        f"🔎 Hiện tại: `{current or 'chưa cấu hình'}`",
        parse_mode="Markdown",
    )


# ---------- 🚀 Auto group ----------

async def _show_auto_status(update: Update):
    groups = await db.auto_groups()
    enabled = (await db.get_setting("auto_enabled")) == "1"
    if not groups:
        PENDING[update.effective_user.id] = "await_auto_group"
        await update.message.reply_text(
            "📌 Gửi *link / username / ID* nhóm cần chạy tự động.",
            parse_mode="Markdown",
        )
        return
    status = "✅ Đang chạy" if enabled else "⏸ Đang tắt"
    lines = [
        "📡 *Trạng thái tự động nhóm*",
        "",
        status,
        "",
        "🆔 Nhóm:",
    ]
    for g in groups:
        lines.append(f"`{g}`")
    lines += ["", "⚙️ Chọn thao tác:"]
    await update.message.reply_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=auto_control_menu()
    )


async def on_admin_auto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    await _show_auto_status(update)


async def on_auto_run(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await db.set_setting("auto_enabled", "1")
    await update.message.reply_text("▶️ Đã bật auto. Bot sẽ gửi dự đoán mỗi phiên mới.")


async def on_auto_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await db.set_setting("auto_enabled", "0")
    await update.message.reply_text("⛔ Đã tắt auto (không xoá nhóm).")


async def on_auto_change(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    PENDING[uid] = "await_auto_group_change"
    await update.message.reply_text("📌 Gửi *link / username / ID* nhóm mới.", parse_mode="Markdown")


# ---------- Other admin ----------

async def on_admin_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    PENDING[uid] = "await_ban"
    await update.message.reply_text(
        "Nhập: `ban <user_id>` để khóa\nhoặc `unban <user_id>` để mở khóa.",
        parse_mode="Markdown",
    )


async def on_admin_users(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    total = await db.count_users()
    active = await db.count_active_today()
    banned = await db.count_banned()
    text = (
        f"👥 Tổng user: *{total}*\n"
        f"🟢 Active hôm nay: *{active}*\n"
        f"🚫 User bị khóa: *{banned}*"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def on_admin_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    PENDING[uid] = "await_broadcast"
    await update.message.reply_text("Gửi nội dung muốn broadcast (text).")


async def on_admin_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    groups = await db.auto_groups()
    source = await get_source()
    enabled = (await db.get_setting("auto_enabled")) == "1"
    text = "⚙️ *Cài đặt bot*\n\n"
    text += f"📡 Nhóm nguồn: `{source or 'chưa cấu hình'}`\n"
    text += f"🚀 Auto: {'✅ bật' if enabled else '⏸ tắt'}\n"
    text += f"🏠 Auto groups: {len(groups)}\n"
    for g in groups:
        text += f"• `{g}`\n"
    await update.message.reply_text(text, parse_mode="Markdown")


# ---------- helpers for verify+save ----------

async def _handle_source_input(update: Update, text: str):
    await update.message.reply_text("⏳ Đang kiểm tra room…")
    ok, info, normalized = await verify_source(text)
    if not ok:
        await update.message.reply_text(
            "❌ Không đọc được room nguồn.\n\n"
            "Kiểm tra:\n• link nhóm\n• session Telegram\n• quyền đọc room\n\n"
            f"Chi tiết: {info}"
        )
        return
    await set_source(normalized)
    from datetime import datetime
    await db.set_setting("source_updated_by", str(update.effective_user.id))
    await db.set_setting("source_updated_at", datetime.utcnow().isoformat())
    await update.message.reply_text(
        f"✅ Đã cập nhật nhóm check lịch sử phiên\n\nNguồn: `{normalized}`",
        parse_mode="Markdown",
        reply_markup=admin_menu(),
    )


async def _handle_auto_group_input(update: Update, text: str, replace: bool):
    norm = _normalize_input(text)
    if norm is None:
        await update.message.reply_text("❌ Không nhận diện được link / username / ID.")
        return
    # We accept it as the broadcast target. For group ids we expect numeric -100…
    if replace:
        # remove previously configured groups
        for g in await db.auto_groups():
            await db.remove_auto_group(g)
    # Verify via telethon if non-numeric, to resolve to numeric id
    target_id = None
    if isinstance(norm, int):
        target_id = norm
    else:
        ok, info, normalized = await verify_source(text)
        if not ok:
            await update.message.reply_text(
                f"❌ Không xác minh được nhóm.\n\nChi tiết: {info}"
            )
            return
        # try to get numeric id from telethon
        from .telethon_client import get_client
        client = await get_client()
        try:
            entity = await client.get_entity(normalized)
            target_id = entity.id
            # ensure -100 prefix for supergroups/channels for Bot API
            if hasattr(entity, "megagroup") or hasattr(entity, "broadcast"):
                target_id = int(f"-100{entity.id}")
        except Exception as e:
            await update.message.reply_text(f"❌ Không lấy được chat id: {e}")
            return

    await db.add_auto_group(target_id)
    await db.set_setting("auto_enabled", "1")
    await update.message.reply_text(
        f"✅ Đã lưu nhóm auto: `{target_id}` và bật chạy.",
        parse_mode="Markdown",
        reply_markup=admin_menu(),
    )


# ---------- main text router ----------

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _track_and_check(update):
        return
    text = (update.message.text or "").strip()
    uid = update.effective_user.id

    # Menu routing
    if text == BTN_PREDICT:
        return await on_predict(update, ctx)
    if text == BTN_STATS:
        return await on_stats(update, ctx)
    if text == BTN_HELP:
        return await cmd_help(update, ctx)
    if text == BTN_ADMIN:
        return await on_admin_entry(update, ctx)
    if text == BTN_BACK:
        return await on_back(update, ctx)

    # Admin-only buttons — silently ignored for non-admins
    if is_admin(uid):
        if text == BTN_ADMIN_AUTO:
            return await on_admin_auto(update, ctx)
        if text == BTN_ADMIN_SOURCE:
            return await on_admin_source(update, ctx)
        if text == BTN_ADMIN_BAN:
            return await on_admin_ban(update, ctx)
        if text == BTN_ADMIN_USERS:
            return await on_admin_users(update, ctx)
        if text == BTN_ADMIN_BROADCAST:
            return await on_admin_broadcast(update, ctx)
        if text == BTN_ADMIN_SETTINGS:
            return await on_admin_settings(update, ctx)
        if text == BTN_AUTO_RUN:
            return await on_auto_run(update, ctx)
        if text == BTN_AUTO_STOP:
            return await on_auto_stop(update, ctx)
        if text == BTN_AUTO_CHANGE:
            return await on_auto_change(update, ctx)

    # Pending admin inputs
    state = PENDING.get(uid)
    if state and is_admin(uid):
        if state == "await_source":
            PENDING.pop(uid, None)
            return await _handle_source_input(update, text)

        if state == "await_auto_group":
            PENDING.pop(uid, None)
            return await _handle_auto_group_input(update, text, replace=False)

        if state == "await_auto_group_change":
            PENDING.pop(uid, None)
            return await _handle_auto_group_input(update, text, replace=True)

        if state == "await_ban":
            PENDING.pop(uid, None)
            parts = text.split()
            if len(parts) != 2 or parts[0].lower() not in ("ban", "unban") or not parts[1].isdigit():
                await update.message.reply_text("❌ Cú pháp sai.")
                return
            tgt = int(parts[1])
            if parts[0].lower() == "ban":
                await db.ban_user(tgt, "admin")
                await update.message.reply_text(f"🔒 Đã khóa user `{tgt}`", parse_mode="Markdown")
            else:
                await db.unban_user(tgt)
                await update.message.reply_text(f"🔓 Đã mở khóa user `{tgt}`", parse_mode="Markdown")
            return

        if state == "await_broadcast":
            PENDING.pop(uid, None)
            uids = await db.all_user_ids()
            ok, fail = 0, 0
            for u in uids:
                try:
                    await ctx.bot.send_message(u, text)
                    ok += 1
                    await asyncio.sleep(0.05)
                except Exception:
                    fail += 1
            await update.message.reply_text(f"📢 Broadcast xong. ✅ {ok} | ❌ {fail}")
            return

    # default
    await update.message.reply_text("Dùng menu bên dưới nhé.", reply_markup=main_menu(uid))


def build_application():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app
