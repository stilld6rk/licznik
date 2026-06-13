from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Boolean, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False)
Session = sessionmaker(bind=engine)
Base = declarative_base()

class GuildMember(Base):
    """Członkowie gildii"""
    __tablename__ = "guild_members"
    
    id = Column(Integer, primary_key=True)
    nick = Column(String(100), unique=True, nullable=False)
    discord_id = Column(Integer, nullable=True)
    join_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    
    # Relacje
    payments = relationship("Payment", back_populates="member")
    corrections = relationship("ManualCorrection", back_populates="recipient")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Payment(Base):
    """Wpłaty ze scrapowania"""
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey("guild_members.id"), nullable=False)
    amount = Column(Float, nullable=False)
    date = Column(DateTime, nullable=False)
    item_name = Column(String(255), nullable=True)  # Np. "Diamenty x10"
    week_start = Column(DateTime, nullable=False)  # Poniedziałek tygodnia
    
    # Relacja
    member = relationship("GuildMember", back_populates="payments")
    
    created_at = Column(DateTime, default=datetime.utcnow)


class ManualCorrection(Base):
    """Ręczne korekty (wpłaty za kogoś)"""
    __tablename__ = "manual_corrections"
    
    id = Column(Integer, primary_key=True)
    recipient_id = Column(Integer, ForeignKey("guild_members.id"), nullable=False)
    payer = Column(String(100), nullable=True)  # Kto zapłacił (tekst bo może nie być w bazie)
    amount = Column(Float, nullable=False)
    date = Column(DateTime, nullable=False)
    week_start = Column(DateTime, nullable=False)
    comment = Column(Text, nullable=True)
    set_by = Column(Integer, nullable=True)  # Discord ID admina co to ustawił
    
    # Relacja
    recipient = relationship("GuildMember", back_populates="corrections")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WeeklyMessage(Base):
    """Przechowuje ID wiadomości Discord dla każdego tygodnia"""
    __tablename__ = "weekly_messages"
    
    id = Column(Integer, primary_key=True)
    week_start = Column(DateTime, unique=True, nullable=False)
    message_id = Column(String(50), nullable=True)
    is_off = Column(Boolean, default=False)  # Czy tydzień wyłączony
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DebtCarryover(Base):
    """Przechowuje przeniesienia długu między tygodniami"""
    __tablename__ = "debt_carryover"
    
    id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey("guild_members.id"), nullable=False)
    week_start = Column(DateTime, nullable=False)
    amount = Column(Float, nullable=False)  # Ujemne = niedopłata, dodatnie = nadpłata
    
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Inicjalizuj tabelę"""
    Base.metadata.create_all(engine)
    print("✅ Baza danych zainicjalizowana")


def get_session():
    """Zwróć nową sesję"""
    return Session()
