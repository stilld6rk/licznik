from sqlalchemy import func
from database import get_session, GuildMember, Payment, ManualCorrection, WeeklyMessage, DebtCarryover, GuildConfig, Vacation
from config import GUILD_ID, RANKING_CHANNEL_ID
from datetime import datetime, timedelta


# ── Guild config ───────────────────────────────────────────────────────────────

def get_guild_config(ranking_channel_id: int):
    """Get config by game guild ID (= ranking_channel_id)."""
    session = get_session()
    try:
        return session.query(GuildConfig).filter_by(ranking_channel_id=ranking_channel_id).first()
    finally:
        session.close()


def get_guild_configs_for_server(discord_guild_id: int) -> list:
    """Get all active configs for a Discord server."""
    session = get_session()
    try:
        return session.query(GuildConfig).filter_by(
            discord_guild_id=discord_guild_id, is_active=True
        ).all()
    finally:
        session.close()


def get_all_active_guild_configs() -> list:
    session = get_session()
    try:
        return session.query(GuildConfig).filter_by(is_active=True).all()
    finally:
        session.close()


def save_guild_config(discord_guild_id: int, guild_name: str, ranking_channel_id: int,
                      role_id: int, admin_role_id: int = 0, member_role_id: int = 0,
                      limit: int = 4, env_key: str = None):
    """Save or update config. Upserts by (discord_guild_id, guild_name) first,
    then by ranking_channel_id, to avoid duplicate configs when channel changes."""
    session = get_session()
    try:
        # Look up by name first — handles re-runs of /setup_gildii with same guild name
        cfg = session.query(GuildConfig).filter_by(
            discord_guild_id=discord_guild_id, guild_name=guild_name
        ).first()

        if cfg and cfg.ranking_channel_id != ranking_channel_id:
            # Channel changed — check if new channel already has a different config
            conflict = session.query(GuildConfig).filter_by(ranking_channel_id=ranking_channel_id).first()
            if conflict and conflict is not cfg:
                session.delete(conflict)

        if not cfg:
            cfg = session.query(GuildConfig).filter_by(ranking_channel_id=ranking_channel_id).first()

        if cfg:
            cfg.discord_guild_id = discord_guild_id
            cfg.guild_name = guild_name
            cfg.ranking_channel_id = ranking_channel_id
            cfg.role_id = role_id
            cfg.admin_role_id = admin_role_id
            cfg.member_role_id = member_role_id
            cfg.limit = limit
            cfg.env_key = env_key or guild_name
            cfg.is_active = True
        else:
            cfg = GuildConfig(
                ranking_channel_id=ranking_channel_id,
                discord_guild_id=discord_guild_id,
                guild_name=guild_name,
                role_id=role_id, admin_role_id=admin_role_id,
                member_role_id=member_role_id, limit=limit,
                env_key=env_key or guild_name,
            )
            session.add(cfg)
        session.commit()
    finally:
        session.close()


def deactivate_guild_config(ranking_channel_id: int):
    session = get_session()
    try:
        cfg = session.query(GuildConfig).filter_by(ranking_channel_id=ranking_channel_id).first()
        if cfg:
            cfg.is_active = False
            session.commit()
            return True
        return False
    finally:
        session.close()


def get_pinned_message_id_for(game_guild_id: int) -> str | None:
    """game_guild_id = ranking_channel_id"""
    session = get_session()
    try:
        cfg = session.query(GuildConfig).filter_by(ranking_channel_id=game_guild_id).first()
        return cfg.pinned_message_id if cfg else None
    finally:
        session.close()


def save_pinned_message_id_for(game_guild_id: int, message_id: str | None):
    """game_guild_id = ranking_channel_id"""
    session = get_session()
    try:
        cfg = session.query(GuildConfig).filter_by(ranking_channel_id=game_guild_id).first()
        if cfg:
            cfg.pinned_message_id = message_id
            session.commit()
    finally:
        session.close()


# ── Members ────────────────────────────────────────────────────────────────────

def deactivate_member(nick: str, guild_id: int = None) -> bool:
    """Mark a member inactive in a specific guild (hides from ranking, keeps history)."""
    gid = guild_id or GUILD_ID
    session = get_session()
    try:
        member = session.query(GuildMember).filter_by(guild_id=gid, nick=nick).first()
        if not member:
            return False
        member.is_active = False
        session.commit()
        return True
    finally:
        session.close()


def rename_member(old_nick: str, new_nick: str, guild_id: int = None) -> str:
    """Rename a member and merge into existing record if new_nick already exists.
    Payments/corrections are a global ledger keyed by nick text, so the rename
    must repoint their `nick` column too — not just the GuildMember row.
    Returns 'renamed', 'merged', or 'not_found'."""
    gid = guild_id or GUILD_ID
    session = get_session()
    try:
        old = session.query(GuildMember).filter_by(guild_id=gid, nick=old_nick).first()
        if not old:
            return 'not_found'

        session.query(Payment).filter(func.lower(Payment.nick) == old_nick.lower()).update(
            {'nick': new_nick}, synchronize_session=False)
        session.query(ManualCorrection).filter(func.lower(ManualCorrection.nick) == old_nick.lower()).update(
            {'nick': new_nick}, synchronize_session=False)

        existing = session.query(GuildMember).filter_by(guild_id=gid, nick=new_nick).first()
        if existing and existing.id != old.id:
            if old.discord_id and not existing.discord_id:
                existing.discord_id = old.discord_id
            if old.join_date and not existing.join_date:
                existing.join_date = old.join_date
            session.delete(old)
            session.commit()
            return 'merged'
        old.nick = new_nick
        session.commit()
        return 'renamed'
    finally:
        session.close()

def get_or_create_member(nick: str, discord_id: int = None, guild_id: int = None,
                         added_manually: bool = False) -> GuildMember:
    gid = guild_id or GUILD_ID
    session = get_session()
    try:
        member = session.query(GuildMember).filter_by(guild_id=gid, nick=nick).first()
        if not member:
            member = GuildMember(guild_id=gid, nick=nick, discord_id=discord_id, added_manually=added_manually)
            session.add(member)
            session.commit()
        elif not added_manually and member.added_manually:
            # Real Discord role scrape found this nick — promote from manual placeholder to real member
            if discord_id:
                member.discord_id = discord_id
            member.added_manually = False
            session.commit()
        elif discord_id and not member.discord_id:
            member.discord_id = discord_id
            session.commit()
        return member
    finally:
        session.close()


def get_all_active_members(guild_id: int = None) -> list:
    gid = guild_id or GUILD_ID
    session = get_session()
    try:
        members = session.query(GuildMember).filter(
            GuildMember.guild_id == gid,
            GuildMember.is_active == True,
            GuildMember.discord_id.isnot(None),
            GuildMember.added_manually == False,
        ).all()
        return [m.nick for m in members]
    finally:
        session.close()


def _update_discord_nick(nick: str, discord_nick: str, guild_id: int = None):
    gid = guild_id or GUILD_ID
    session = get_session()
    try:
        member = session.query(GuildMember).filter_by(guild_id=gid, nick=nick).first()
        if member and member.discord_nick != discord_nick:
            member.discord_nick = discord_nick
            session.commit()
    finally:
        session.close()


def update_member_join_date(nick: str, join_date: datetime, force: bool = False, guild_id: int = None):
    gid = guild_id or GUILD_ID
    session = get_session()
    try:
        member = session.query(GuildMember).filter_by(guild_id=gid, nick=nick).first()
        if member:
            if not member.join_date or force:
                member.join_date = join_date
                session.commit()
                return True
        return False
    finally:
        session.close()


def get_member_info(nick: str, guild_id: int = None):
    gid = guild_id or GUILD_ID
    session = get_session()
    try:
        member = session.query(GuildMember).filter_by(guild_id=gid, nick=nick).first()
        if member:
            return {
                'nick': member.nick,
                'discord_id': member.discord_id,
                'join_date': member.join_date,
                'is_active': member.is_active,
                'created_at': member.created_at
            }
        return None
    finally:
        session.close()


# ── Payments ───────────────────────────────────────────────────────────────────

def add_payment(nick: str, amount: float, date: datetime, item_name: str = None,
                source_guild_name: str = None):
    """Payments are a global ledger keyed by nick — not tied to any guild."""
    session = get_session()
    try:
        week_start = (date - timedelta(days=date.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        payment = Payment(
            nick=nick, source_guild_name=source_guild_name,
            amount=amount, date=date, item_name=item_name, week_start=week_start,
        )
        session.add(payment)
        session.commit()
    finally:
        session.close()


def add_manual_correction(recipient_nick: str, amount: float, date: datetime,
                          payer: str = None, comment: str = None, set_by: int = None,
                          guild_id: int = None, discord_id: int = None):
    """The correction itself is a global ledger entry keyed by nick. `guild_id`
    is only used to ensure a roster placeholder exists in the guild the command
    was invoked from (exempt from role-loss cleanup, visible on that roster)."""
    gid = guild_id or GUILD_ID
    session = get_session()
    try:
        # added_manually exempts from role-loss cleanup; use real discord_id when available
        get_or_create_member(recipient_nick, discord_id=discord_id or 0, guild_id=gid, added_manually=True)
        week_start = (date - timedelta(days=date.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        correction = ManualCorrection(
            nick=recipient_nick, payer=payer, amount=amount,
            date=date, week_start=week_start, comment=comment, set_by=set_by
        )
        session.add(correction)
        session.commit()
    finally:
        session.close()


def get_corrections_for_week(week_start: datetime, guild_id: int = None) -> dict:
    """Corrections are a global ledger; scope here to nicks on this guild's active roster."""
    gid = guild_id or GUILD_ID
    session = get_session()
    try:
        members = session.query(GuildMember).filter(
            GuildMember.guild_id == gid,
            GuildMember.is_active == True,
            GuildMember.discord_id.isnot(None),
            GuildMember.added_manually == False,
        ).all()
        nick_map = {m.nick.lower(): m.nick for m in members}
        if not nick_map:
            return {}

        corrections = session.query(ManualCorrection).filter(
            func.lower(ManualCorrection.nick).in_(nick_map.keys()),
            ManualCorrection.week_start == week_start
        ).all()
        result = {}
        for corr in corrections:
            canonical = nick_map.get(corr.nick.lower())
            if not canonical:
                continue
            result.setdefault(canonical, []).append(corr)
        return result
    finally:
        session.close()


def set_week_off(week_start: datetime, is_off: bool = True, guild_id: int = None):
    gid = guild_id or GUILD_ID
    session = get_session()
    try:
        msg = session.query(WeeklyMessage).filter_by(guild_id=gid, week_start=week_start).first()
        if msg:
            msg.is_off = is_off
        else:
            msg = WeeklyMessage(guild_id=gid, week_start=week_start, is_off=is_off)
            session.add(msg)
        session.commit()
    finally:
        session.close()


def is_week_off(week_start: datetime, guild_id: int = None) -> bool:
    gid = guild_id or GUILD_ID
    session = get_session()
    try:
        msg = session.query(WeeklyMessage).filter_by(guild_id=gid, week_start=week_start).first()
        return msg.is_off if msg else False
    finally:
        session.close()


def delete_correction(correction_id: int):
    """Corrections are a global ledger — deletable by any guild's admin."""
    session = get_session()
    try:
        corr = session.query(ManualCorrection).filter_by(id=correction_id).first()
        if corr:
            session.delete(corr)
            session.commit()
            return True
        return False
    finally:
        session.close()


def get_all_payments_grouped(guild_id: int = None) -> dict:
    """Return payments grouped by (week_start, nick) for members of guild_id.
    Payments looked up by nick only — all source guilds included."""
    gid = guild_id or GUILD_ID
    session = get_session()
    try:
        members = session.query(GuildMember).filter(
            GuildMember.guild_id == gid,
            GuildMember.is_active == True,
            GuildMember.discord_id.isnot(None),
            GuildMember.added_manually == False,
        ).all()
        nicks = [m.nick for m in members]
        if not nicks:
            return {}

        lower_nicks = [n.lower() for n in nicks]
        nick_map = {n.lower(): n for n in nicks}

        results = session.query(
            Payment.week_start,
            Payment.nick,
            func.sum(Payment.amount).label('total')
        ).filter(
            func.lower(Payment.nick).in_(lower_nicks)
        ).group_by(Payment.week_start, Payment.nick).all()

        grouped = {}
        for week_start, p_nick, total in results:
            canonical = nick_map.get((p_nick or '').lower())
            if not canonical:
                continue
            ws = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            grouped.setdefault(ws, {})[canonical] = grouped.get(ws, {}).get(canonical, 0) + float(total or 0)
        return grouped
    finally:
        session.close()


def get_all_corrections_grouped(guild_id: int = None) -> dict:
    """Corrections are a global ledger; scope here to nicks on this guild's active roster."""
    gid = guild_id or GUILD_ID
    session = get_session()
    try:
        members = session.query(GuildMember).filter(
            GuildMember.guild_id == gid,
            GuildMember.is_active == True,
            GuildMember.discord_id.isnot(None),
            GuildMember.added_manually == False,
        ).all()
        nicks = [m.nick for m in members]
        if not nicks:
            return {}
        lower_nicks = [n.lower() for n in nicks]
        nick_map = {n.lower(): n for n in nicks}

        results = session.query(ManualCorrection).filter(
            func.lower(ManualCorrection.nick).in_(lower_nicks)
        ).all()

        grouped = {}
        for corr in results:
            canonical = nick_map.get((corr.nick or '').lower())
            if not canonical:
                continue
            ws = corr.week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            grouped.setdefault(ws, {})[canonical] = grouped.get(ws, {}).get(canonical, 0) + float(corr.amount)
        return grouped
    finally:
        session.close()


def get_all_logs_for_nick(nick: str) -> dict:
    """Return all logs for a nick — payments and corrections are both a global
    ledger, independent of any guild. Returns None only if the nick has no
    roster record anywhere and no ledger history at all."""
    session = get_session()
    try:
        member = session.query(GuildMember).filter(
            func.lower(GuildMember.nick) == nick.lower()
        ).first()
        payments = session.query(Payment).filter(
            func.lower(Payment.nick) == nick.lower()
        ).order_by(Payment.date.desc()).all()
        corrections = session.query(ManualCorrection).filter(
            func.lower(ManualCorrection.nick) == nick.lower()
        ).order_by(ManualCorrection.date.desc()).all()

        if not member and not payments and not corrections:
            return None

        display_nick = member.nick if member else nick
        discord_nick = (member.discord_nick or member.nick) if member else nick
        return {
            'nick': display_nick,
            'discord_nick': discord_nick,
            'payments': [
                {'date': p.date, 'amount': p.amount, 'item': p.item_name,
                 'week_start': p.week_start, 'source_guild': p.source_guild_name}
                for p in payments
            ],
            'corrections': [
                {'date': c.date, 'amount': c.amount, 'payer': c.payer,
                 'comment': c.comment, 'week_start': c.week_start}
                for c in corrections
            ],
        }
    finally:
        session.close()


def get_corrections_for_nick(nick: str) -> list:
    """Corrections are a global ledger — no guild scoping."""
    session = get_session()
    try:
        corrections = session.query(ManualCorrection).filter(
            func.lower(ManualCorrection.nick) == nick.strip().lower()
        ).order_by(ManualCorrection.date.desc()).all()
        return [
            {'id': c.id, 'date': c.date, 'amount': c.amount, 'payer': c.payer, 'comment': c.comment, 'week_start': c.week_start}
            for c in corrections
        ]
    finally:
        session.close()


def clear_all_payments() -> int:
    """Delete all rows from the payments table. Manual corrections are NOT touched.
    Returns the number of deleted rows."""
    session = get_session()
    try:
        deleted = session.query(Payment).delete()
        session.commit()
        return deleted
    finally:
        session.close()


def update_correction(correction_id: int, amount: float = None, comment: str = None) -> bool:
    session = get_session()
    try:
        corr = session.query(ManualCorrection).filter_by(id=correction_id).first()
        if not corr:
            return False
        if amount is not None:
            corr.amount = amount
        if comment is not None:
            corr.comment = comment if comment.strip() else None
        session.commit()
        return True
    finally:
        session.close()


def get_corrections_with_comments(week_start: datetime, guild_id: int = None) -> dict:
    gid = guild_id or GUILD_ID
    session = get_session()
    try:
        members = session.query(GuildMember).filter(
            GuildMember.guild_id == gid,
            GuildMember.is_active == True,
            GuildMember.discord_id.isnot(None),
            GuildMember.added_manually == False,
        ).all()
        nicks = [m.nick for m in members]
        if not nicks:
            return {}
        lower_nicks = [n.lower() for n in nicks]
        nick_map = {n.lower(): n for n in nicks}

        results = session.query(ManualCorrection).filter(
            func.lower(ManualCorrection.nick).in_(lower_nicks),
            ManualCorrection.week_start == week_start,
            ManualCorrection.comment.isnot(None)
        ).all()
        grouped = {}
        for corr in results:
            canonical = nick_map.get((corr.nick or '').lower())
            if not canonical:
                continue
            grouped.setdefault(canonical, []).append((int(corr.amount), corr.comment))
        return grouped
    finally:
        session.close()


def _get_all_member_info(guild_id: int = None) -> dict:
    gid = guild_id or GUILD_ID
    session = get_session()
    try:
        members = session.query(GuildMember).filter(
            GuildMember.guild_id == gid,
            GuildMember.is_active == True,
            GuildMember.discord_id.isnot(None),
            GuildMember.added_manually == False,
        ).all()
        return {
            m.nick: {
                'join_date': m.join_date,
                'discord_nick': m.discord_nick or m.nick,
            }
            for m in members
        }
    finally:
        session.close()


# ── Vacations (urlop) ──────────────────────────────────────────────────────────
# Global by nick, like payments/corrections — exempts a player from payment
# requirements for any week overlapping [start_date, end_date], across all guilds.

def add_vacation(nick: str, start_date: datetime, end_date: datetime,
                 comment: str = None, set_by: int = None) -> int:
    session = get_session()
    try:
        vacation = Vacation(
            nick=nick, start_date=start_date, end_date=end_date,
            comment=comment, set_by=set_by,
        )
        session.add(vacation)
        session.commit()
        return vacation.id
    finally:
        session.close()


def get_vacations_for_nick(nick: str) -> list:
    session = get_session()
    try:
        vacations = session.query(Vacation).filter(
            func.lower(Vacation.nick) == nick.strip().lower()
        ).order_by(Vacation.start_date.desc()).all()
        return [
            {'id': v.id, 'start_date': v.start_date, 'end_date': v.end_date, 'comment': v.comment}
            for v in vacations
        ]
    finally:
        session.close()


def delete_vacation(vacation_id: int) -> bool:
    session = get_session()
    try:
        vacation = session.query(Vacation).filter_by(id=vacation_id).first()
        if not vacation:
            return False
        session.delete(vacation)
        session.commit()
        return True
    finally:
        session.close()


def get_all_vacations_grouped() -> dict:
    """nick.lower() -> [(start_date, end_date), ...], for weekly exemption checks."""
    session = get_session()
    try:
        vacations = session.query(Vacation).all()
        grouped = {}
        for v in vacations:
            grouped.setdefault(v.nick.lower(), []).append((v.start_date, v.end_date))
        return grouped
    finally:
        session.close()


# Legacy helpers — kept for backward compat with old env-var single-guild deploys
def get_pinned_message_id() -> str | None:
    return get_pinned_message_id_for(RANKING_CHANNEL_ID)


def save_pinned_message_id(message_id: str | None):
    save_pinned_message_id_for(RANKING_CHANNEL_ID, message_id)
