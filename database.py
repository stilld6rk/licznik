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
    guild_id = Column(BigInteger, nullable=False, default=0)  # = GuildConfig.ranking_channel_id
    nick = Column(String(100), nullable=False)
    discord_nick = Column(String(100), nullable=True)
    discord_id = Column(BigInteger, nullable=True)
    join_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    added_manually = Column(Boolean, nullable=False, default=False)  # created via /wpłata_ręczna, exempt from role-loss cleanup

    __table_args__ = (UniqueConstraint('guild_id', 'nick', name='uq_guild_nick'),)

    payments = relationship("Payment", back_populates="member")
    corrections = relationship("ManualCorrection", back_populates="recipient")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey("guild_members.id"), nullable=True)
    # Denormalized nick for cross-guild lookup without joins
    nick = Column(String(100), nullable=True)
    # Which game guild's treasury log this payment came from
    source_guild_name = Column(String(100), nullable=True)
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
    guild_id = Column(BigInteger, nullable=False, default=0)  # = GuildConfig.ranking_channel_id
    week_start = Column(DateTime, nullable=False)
    message_id = Column(String(50), nullable=True)
    is_off = Column(Boolean, default=False)

    __table_args__ = (UniqueConstraint('guild_id', 'week_start', name='uq_guild_week'),)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GuildConfig(Base):
    __tablename__ = "guild_configs"

    # PK = ranking channel ID — unique per game guild
    ranking_channel_id = Column(BigInteger, primary_key=True)
    # Discord server ID — multiple game guilds can share one Discord server
    discord_guild_id = Column(BigInteger, nullable=False, default=0)
    guild_name = Column(String(100), nullable=False, default="Gildia")
    role_id = Column(BigInteger, default=0)
    admin_role_id = Column(BigInteger, default=0)
    member_role_id = Column(BigInteger, default=0)
    limit = Column(Integer, default=4)
    pinned_message_id = Column(String(50), nullable=True)
    env_key = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint('discord_guild_id', 'guild_name', name='uq_discord_guild_name'),)


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
            "ALTER TABLE guild_members DROP CONSTRAINT IF EXISTS guild_members_nick_key",
            "ALTER TABLE weekly_messages DROP CONSTRAINT IF EXISTS weekly_messages_week_start_key",
            "ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS pinned_message_id VARCHAR(50)",
            "ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS env_key VARCHAR(50)",
            # Multi-guild: add discord_guild_id column
            "ALTER TABLE guild_configs ADD COLUMN IF NOT EXISTS discord_guild_id BIGINT NOT NULL DEFAULT 0",
            "UPDATE guild_configs SET discord_guild_id = guild_id WHERE discord_guild_id = 0",
            # Migrate guild_members.guild_id: Discord server ID → ranking_channel_id
            """UPDATE guild_members gm SET guild_id = gc.ranking_channel_id
               FROM guild_configs gc
               WHERE gc.guild_id = gm.guild_id
                 AND gm.guild_id != gc.ranking_channel_id
                 AND gc.ranking_channel_id IS NOT NULL AND gc.ranking_channel_id != 0""",
            # Migrate weekly_messages.guild_id
            """UPDATE weekly_messages wm SET guild_id = gc.ranking_channel_id
               FROM guild_configs gc
               WHERE gc.guild_id = wm.guild_id
                 AND wm.guild_id != gc.ranking_channel_id
                 AND gc.ranking_channel_id IS NOT NULL AND gc.ranking_channel_id != 0""",
            # Change GuildConfig PK from guild_id to ranking_channel_id
            "ALTER TABLE guild_configs DROP CONSTRAINT IF EXISTS guild_configs_pkey",
            "ALTER TABLE guild_configs ADD PRIMARY KEY (ranking_channel_id)",
            "ALTER TABLE guild_configs ADD CONSTRAINT IF NOT EXISTS uq_discord_guild_name UNIQUE (discord_guild_id, guild_name)",
            # Clean up orphaned members: no discord_id, no payments, no corrections
            """DELETE FROM guild_members WHERE discord_id IS NULL
               AND id NOT IN (SELECT DISTINCT member_id FROM payments)
               AND id NOT IN (SELECT DISTINCT recipient_id FROM manual_corrections)""",
            # Set discord_id=0 for members that have corrections but discord_id IS NULL
            """UPDATE guild_members SET discord_id = 0
               WHERE discord_id IS NULL
               AND id IN (SELECT DISTINCT recipient_id FROM manual_corrections)""",
            # Explicit flag for manually-added members instead of overloading discord_id=0.
            # Only flag members with discord_id=0 AND no scraped payment history — members
            # with real payments are legacy scraped junk, not /wpłata_ręczna entries, and
            # must remain eligible for role-loss cleanup.
            "ALTER TABLE guild_members ADD COLUMN IF NOT EXISTS added_manually BOOLEAN NOT NULL DEFAULT false",
            """UPDATE guild_members SET added_manually = true
               WHERE discord_id = 0
               AND id NOT IN (SELECT DISTINCT member_id FROM payments)""",
            # Deactivate duplicate configs: keep only the latest ranking_channel_id per (discord_guild_id, guild_name)
            """UPDATE guild_configs SET is_active = false
               WHERE is_active = true
               AND ranking_channel_id NOT IN (
                   SELECT MAX(ranking_channel_id)
                   FROM guild_configs
                   WHERE is_active = true
                   GROUP BY discord_guild_id, guild_name
               )""",
            # Cross-guild payments: add nick + source_guild_name columns
            "ALTER TABLE payments ADD COLUMN IF NOT EXISTS nick VARCHAR(100)",
            "ALTER TABLE payments ADD COLUMN IF NOT EXISTS source_guild_name VARCHAR(100)",
            # Backfill nick from guild_members via member_id FK
            """UPDATE payments p SET nick = gm.nick
               FROM guild_members gm
               WHERE gm.id = p.member_id AND p.nick IS NULL""",
            # Fix source_guild_name that was incorrectly stored as a channel ID (numeric string)
            # by looking up the guild_name from guild_configs
            """UPDATE payments p SET source_guild_name = gc.guild_name
               FROM guild_members gm
               JOIN guild_configs gc ON gc.ranking_channel_id = gm.guild_id
               WHERE gm.id = p.member_id
                 AND (p.source_guild_name IS NULL OR p.source_guild_name ~ '^[0-9]+$')""",
            # Remove duplicate payments: same nick+date+amount = same physical payment
            """DELETE FROM payments WHERE id NOT IN (
               SELECT MIN(id) FROM payments
               WHERE nick IS NOT NULL
               GROUP BY LOWER(nick), date, amount)
               AND nick IS NOT NULL""",
            # Delete any remaining orphaned payments with no nick and no valid member
            """DELETE FROM payments WHERE nick IS NULL
               AND (member_id IS NULL OR member_id NOT IN (SELECT id FROM guild_members))""",
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
