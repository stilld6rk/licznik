from sqlalchemy import create_engine, Column, Integer, BigInteger, String, DateTime, Float, Boolean, ForeignKey, Text, text, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False)
Session = sessionmaker(bind=engine)
Base = declarative_base()

class GuildMember(Base):
    __tablename__ = "guild_members"

    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger, nullable=False, default=0)
    nick = Column(String(100), nullable=False)
    discord_nick = Column(String(100), nullable=True)
    discord_id = Column(BigInteger, nullable=True)
    join_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    __table_args__ = (UniqueConstraint('guild_id', 'nick', name='uq_guild_nick'),)

    payments = relationship("Payment", back_populates="member")
    corrections = relationship("ManualCorrection", back_populates="recipient")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey("guild_members.id"), nullable=False)
    amount = Column(Float, nullable=False)
    date = Column(DateTime, nullable=False)
    item_name = Column(String(255), nullable=True)
    week_start = Column(DateTime, nullable=False)

    member = relationship("GuildMember", back_populates="payments")
    created_at = Column(DateTime, default=datetime.utcnow)


class ManualCorrection(Base):
    __tablename__ = "manual_corrections"

    id = Column(Integer, primary_key=True)
    recipient_id = Column(Integer, ForeignKey("guild_members.id"), nullable=False)
    payer = Column(String(100), nullable=True)
    amount = Column(Float, nullable=False)
    date = Column(DateTime, nullable=False)
    week_start = Column(DateTime, nullable=False)
    comment = Column(Text, nullable=True)
    set_by = Column(BigInteger, nullable=True)

    recipient = relationship("GuildMember", back_populates="corrections")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WeeklyMessage(Base):
    __tablename__ = "weekly_messages"

    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger, nullable=False, default=0)
    week_start = Column(DateTime, nullable=False)
    message_id = Column(String(50), nullable=True)
    is_off = Column(Boolean, default=False)

    __table_args__ = (UniqueConstraint('guild_id', 'week_start', name='uq_guild_week'),)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GuildConfig(Base):
    __tablename__ = "guild_configs"

    guild_id = Column(BigInteger, primary_key=True)
    guild_name = Column(String(100), nullable=False, default="Gildia")
    ranking_channel_id = Column(BigInteger, nullable=True)
    role_id = Column(BigInteger, default=0)
    admin_role_id = Column(BigInteger, default=0)
    member_role_id = Column(BigInteger, default=0)
    limit = Column(Integer, default=4)
    pinned_message_id = Column(String(50), nullable=True)
    env_key = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DebtCarryover(Base):
    __tablename__ = "debt_carryover"

    id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey("guild_members.id"), nullable=False)
    week_start = Column(DateTime, nullable=False)
    amount = Column(Float, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        migrations = [
            "ALTER TABLE guild_members ALTER COLUMN discord_id TYPE BIGINT",
            "ALTER TABLE manual_corrections ALTER COLUMN set_by TYPE BIGINT",
            "ALTER TABLE guild_members ADD COLUMN IF NOT EXISTS discord_nick VARCHAR(100)",
            "ALTER TABLE guild_members ADD COLUMN IF NOT EXISTS guild_id BIGINT NOT NULL DEFAULT 0",
            "ALTER TABLE weekly_messages ADD COLUMN IF NOT EXISTS guild_id BIGINT NOT NULL DEFAULT 0",
            # Drop old unique constraints that don't include guild_id
            "ALTER TABLE guild_members DROP CONSTRAINT IF EXISTS guild_members_nick_key",
            "ALTER TABLE weekly_messages DROP CONSTRAINT IF EXISTS weekly_messages_week_start_key",
            "ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS pinned_message_id VARCHAR(50)",
            "ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS env_key VARCHAR(50)",
        ]
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                conn.rollback()
    print("✅ Baza danych zainicjalizowana")


def get_session():
    return Session()
