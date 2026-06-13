from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from database import get_session, GuildMember, Payment, ManualCorrection, WeeklyMessage, DebtCarryover
from datetime import datetime, timedelta
import re


def get_or_create_member(nick: str, discord_id: int = None) -> GuildMember:
    """Pobrań lub stwórz członka"""
    session = get_session()
    try:
        member = session.query(GuildMember).filter_by(nick=nick).first()
        if not member:
            member = GuildMember(nick=nick, discord_id=discord_id)
            session.add(member)
            session.commit()
        elif discord_id and not member.discord_id:
            member.discord_id = discord_id
            session.commit()
        return member
    finally:
        session.close()


def get_all_active_members() -> list:
    """Zwróć wszystkich aktywnych członków"""
    session = get_session()
    try:
        members = session.query(GuildMember).filter_by(is_active=True).all()
        return [m.nick for m in members]
    finally:
        session.close()


def update_member_join_date(nick: str, join_date: datetime, force: bool = False):
    """Aktualizuj datę dołączenia (force=True pozwala na zmianę istniejącej daty)"""
    session = get_session()
    try:
        member = session.query(GuildMember).filter_by(nick=nick).first()
        if member:
            if not member.join_date or force:
                member.join_date = join_date
                session.commit()
                return True
        return False
    finally:
        session.close()


def get_member_info(nick: str):
    """Pobierz informacje o członku"""
    session = get_session()
    try:
        member = session.query(GuildMember).filter_by(nick=nick).first()
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


def add_payment(nick: str, amount: float, date: datetime, item_name: str = None):
    """Dodaj wpłatę"""
    session = get_session()
    try:
        member = get_or_create_member(nick)
        week_start = (date - timedelta(days=date.weekday())).replace(hour=0, minute=0, second=0)
        
        payment = Payment(
            member_id=member.id,
            amount=amount,
            date=date,
            item_name=item_name,
            week_start=week_start
        )
        session.add(payment)
        session.commit()
    finally:
        session.close()


def add_manual_correction(recipient_nick: str, amount: float, date: datetime, 
                         payer: str = None, comment: str = None, set_by: int = None):
    """Dodaj ręczną korektę"""
    session = get_session()
    try:
        recipient = get_or_create_member(recipient_nick)
        week_start = (date - timedelta(days=date.weekday())).replace(hour=0, minute=0, second=0)
        
        correction = ManualCorrection(
            recipient_id=recipient.id,
            payer=payer,
            amount=amount,
            date=date,
            week_start=week_start,
            comment=comment,
            set_by=set_by
        )
        session.add(correction)
        session.commit()
    finally:
        session.close()


def get_payments_for_week(week_start: datetime) -> dict:
    """Zwróć słownik {nick: total_amount} dla danego tygodnia"""
    session = get_session()
    try:
        results = session.query(
            GuildMember.nick,
            func.sum(Payment.amount).label('total')
        ).join(Payment).filter(
            Payment.week_start == week_start
        ).group_by(GuildMember.nick).all()
        
        return {nick: total or 0 for nick, total in results}
    finally:
        session.close()


def get_corrections_for_week(week_start: datetime) -> dict:
    """Zwróć słownik {nick: list_of_corrections} dla danego tygodnia"""
    session = get_session()
    try:
        corrections = session.query(ManualCorrection).filter(
            ManualCorrection.week_start == week_start
        ).all()
        
        result = {}
        for corr in corrections:
            nick = corr.recipient.nick
            if nick not in result:
                result[nick] = []
            result[nick].append(corr)
        
        return result
    finally:
        session.close()


def get_carryover_debt(member_nick: str, week_start: datetime) -> float:
    """Zwróć przeniesiony dług z poprzedniego tygodnia"""
    session = get_session()
    try:
        member = session.query(GuildMember).filter_by(nick=member_nick).first()
        if not member:
            return 0
        
        carryover = session.query(DebtCarryover).filter(
            DebtCarryover.member_id == member.id,
            DebtCarryover.week_start == week_start
        ).first()
        
        return carryover.amount if carryover else 0
    finally:
        session.close()


def set_carryover_debt(member_nick: str, week_start: datetime, amount: float):
    """Ustawić przeniesiony dług"""
    session = get_session()
    try:
        member = get_or_create_member(member_nick)
        
        carryover = session.query(DebtCarryover).filter(
            DebtCarryover.member_id == member.id,
            DebtCarryover.week_start == week_start
        ).first()
        
        if carryover:
            carryover.amount = amount
        else:
            carryover = DebtCarryover(
                member_id=member.id,
                week_start=week_start,
                amount=amount
            )
            session.add(carryover)
        
        session.commit()
    finally:
        session.close()


def save_weekly_message(week_start: datetime, message_id: str):
    """Zapisz ID wiadomości Discord dla tygodnia"""
    session = get_session()
    try:
        msg = session.query(WeeklyMessage).filter_by(week_start=week_start).first()
        
        if msg:
            msg.message_id = message_id
        else:
            msg = WeeklyMessage(week_start=week_start, message_id=message_id)
            session.add(msg)
        
        session.commit()
    finally:
        session.close()


def get_weekly_message(week_start: datetime) -> str:
    """Pobierz ID wiadomości Discord dla tygodnia"""
    session = get_session()
    try:
        msg = session.query(WeeklyMessage).filter_by(week_start=week_start).first()
        return msg.message_id if msg else None
    finally:
        session.close()


def set_week_off(week_start: datetime, is_off: bool = True):
    """Ustaw/usuń tydzień jako wyłączony"""
    session = get_session()
    try:
        msg = session.query(WeeklyMessage).filter_by(week_start=week_start).first()
        
        if msg:
            msg.is_off = is_off
        else:
            msg = WeeklyMessage(week_start=week_start, is_off=is_off)
            session.add(msg)
        
        session.commit()
    finally:
        session.close()


def is_week_off(week_start: datetime) -> bool:
    """Sprawdź czy tydzień wyłączony"""
    session = get_session()
    try:
        msg = session.query(WeeklyMessage).filter_by(week_start=week_start).first()
        return msg.is_off if msg else False
    finally:
        session.close()


def delete_correction(correction_id: int):
    """Usuń korektę"""
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


def get_all_weeks() -> list:
    """Pobierz wszystkie tygodnie z danymi"""
    session = get_session()
    try:
        weeks = session.query(func.distinct(Payment.week_start)).all()
        return sorted([w[0] for w in weeks if w[0]], reverse=True)
    finally:
        session.close()


_PINNED_SENTINEL = datetime(1970, 1, 1)


def get_pinned_message_id() -> str | None:
    """Pobierz ID przypiętej wiadomości rankingowej"""
    session = get_session()
    try:
        msg = session.query(WeeklyMessage).filter_by(week_start=_PINNED_SENTINEL).first()
        return msg.message_id if msg else None
    finally:
        session.close()


def save_pinned_message_id(message_id: str):
    """Zapisz ID przypiętej wiadomości rankingowej"""
    session = get_session()
    try:
        msg = session.query(WeeklyMessage).filter_by(week_start=_PINNED_SENTINEL).first()
        if msg:
            msg.message_id = message_id
        else:
            msg = WeeklyMessage(week_start=_PINNED_SENTINEL, message_id=message_id)
            session.add(msg)
        session.commit()
    finally:
        session.close()
