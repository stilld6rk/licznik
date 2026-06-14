import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
from config import DISCORD_BOT_TOKEN, GUILD_ID, ROLE_ID, ADMIN_ROLE_ID, MEMBER_ROLE_ID, GOLD, ORANGE, RED, GREEN, RANKING_CHANNEL_ID, GUILD_NAME
from db_helper import (
    get_or_create_member, add_manual_correction, get_all_active_members,
    is_week_off, set_week_off, delete_correction, get_corrections_for_week,
    get_all_logs_for_nick, get_corrections_for_nick, update_correction,
    get_pinned_message_id_for, save_pinned_message_id_for,
    save_guild_config, get_guild_config, get_all_active_guild_configs,
)
from calculator import build_ranking_content
from scraper import run_scraper
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _get_cfg(guild_id: int):
    """Pobierz konfigurację guildu z DB lub użyj env vars jako fallback."""
    cfg = get_guild_config(guild_id)
    if cfg:
        return cfg
    # Legacy fallback — zwraca obiekt-like ze zmiennych środowiskowych
    class _Env:
        pass
    e = _Env()
    e.guild_id = GUILD_ID
    e.guild_name = GUILD_NAME
    e.ranking_channel_id = RANKING_CHANNEL_ID
    e.role_id = ROLE_ID
    e.admin_role_id = ADMIN_ROLE_ID
    e.member_role_id = MEMBER_ROLE_ID
    e.limit = 4
    return e


def is_admin(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    cfg = _get_cfg(interaction.guild_id)
    if cfg.admin_role_id:
        return any(r.id == cfg.admin_role_id for r in interaction.user.roles)
    return False


def is_member(interaction: discord.Interaction) -> bool:
    if is_admin(interaction):
        return True
    cfg = _get_cfg(interaction.guild_id)
    if cfg.member_role_id:
        return any(r.id == cfg.member_role_id for r in interaction.user.roles)
    return False


intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


class HistoriaModal(discord.ui.Modal, title="Historia wpłat"):
    nick = discord.ui.TextInput(
        label="Nick gracza",
        placeholder="Wpisz nick z gry lub Discord...",
        min_length=1,
        max_length=100,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        import asyncio
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, get_all_logs_for_nick, self.nick.value.strip(), interaction.guild_id
        )

        if not data:
            await interaction.followup.send(f"❌ Nie znaleziono gracza: **{self.nick.value}**", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📜 Historia wpłat: {data['discord_nick']}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        if data['corrections']:
            lines = []
            for c in data['corrections']:
                line = f"`{c['week_start'].strftime('%d.%m')}` **+{int(c['amount'])}💎**"
                if c['payer']:
                    line += f" od {c['payer']}"
                if c['comment']:
                    line += f" — *{c['comment']}*"
                lines.append(line)
            embed.add_field(
                name=f"✍️ Wpłaty ręczne ({len(data['corrections'])})",
                value="\n".join(lines[:20]) + ("…" if len(lines) > 20 else ""),
                inline=False
            )
        else:
            embed.add_field(name="✍️ Wpłaty ręczne", value="*Brak*", inline=False)

        if data['payments']:
            from collections import defaultdict
            by_week = defaultdict(float)
            for p in data['payments']:
                by_week[p['week_start']] += p['amount']
            lines = [
                f"`{ws.strftime('%d.%m.%Y')}` **{int(total)}💎**"
                for ws, total in sorted(by_week.items(), reverse=True)
            ]
            embed.add_field(
                name=f"🎮 Wpłaty z gry ({len(by_week)} tygodni, łącznie {int(sum(by_week.values()))}💎)",
                value="\n".join(lines[:20]) + ("…" if len(lines) > 20 else ""),
                inline=False
            )
        else:
            embed.add_field(name="🎮 Wpłaty z gry", value="*Brak*", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)


class RankingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📜 Historia wpłat", style=discord.ButtonStyle.secondary, custom_id="historia_btn")
    async def historia_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(HistoriaModal())


@bot.event
async def on_guild_join(guild: discord.Guild):
    """Sync commands when bot joins a new server."""
    try:
        g = discord.Object(id=guild.id)
        bot.tree.copy_global_to(guild=g)
        synced = await bot.tree.sync(guild=g)
        logger.info(f"✅ Nowy serwer {guild.name} ({guild.id}) — zsynchronizowano {len(synced)} komend")
    except Exception as e:
        logger.error(f"❌ Błąd synchronizacji dla {guild.name}: {e}")


@bot.event
async def on_ready():
    logger.info(f"✅ Bot zalogowany jako {bot.user}")
    bot.add_view(RankingView())

    try:
        synced = await bot.tree.sync()
        logger.info(f"✅ Zsynchronizowano {len(synced)} komend globalnie")
    except Exception as e:
        logger.error(f"❌ Błąd synchronizacji: {e}")

    import asyncio
    loop = asyncio.get_event_loop()
    logger.info("🔄 Startup: scraper → ranking")
    await loop.run_in_executor(None, run_scraper)
    await update_all_rankings()

    if not auto_scrape.is_running():
        auto_scrape.start()


async def update_ranking(guild_id: int):
    """Edytuj lub wyślij wiadomość rankingową dla konkretnego guildu."""
    cfg = _get_cfg(guild_id)
    if not cfg or not cfg.ranking_channel_id:
        logger.warning(f"⚠️  Brak konfiguracji rankingu dla guildu {guild_id}")
        return

    channel = bot.get_channel(cfg.ranking_channel_id)
    if not channel:
        logger.error(f"❌ Nie znaleziono kanału {cfg.ranking_channel_id}")
        return

    import asyncio
    loop = asyncio.get_event_loop()
    content = await loop.run_in_executor(
        None, build_ranking_content, guild_id, cfg.guild_name, cfg.limit
    )
    view = RankingView()

    # 1. Try stored message ID from GuildConfig
    msg_id = get_pinned_message_id_for(guild_id)
    if msg_id:
        try:
            msg = await channel.fetch_message(int(msg_id))
            await msg.edit(content=content, view=view)
            logger.info(f"✏️  [{cfg.guild_name}] Zaktualizowano wiadomość {msg_id}")
            return
        except discord.NotFound:
            logger.warning(f"⚠️  [{cfg.guild_name}] Stara wiadomość usunięta, szukam w historii...")
            save_pinned_message_id_for(guild_id, None)

    # 2. Scan last 50 messages in channel for bot's own message
    try:
        async for msg in channel.history(limit=50):
            if msg.author == bot.user:
                await msg.edit(content=content, view=view)
                save_pinned_message_id_for(guild_id, str(msg.id))
                logger.info(f"🔍 [{cfg.guild_name}] Znaleziono wiadomość {msg.id} w historii")
                return
    except Exception as e:
        logger.warning(f"⚠️  [{cfg.guild_name}] Błąd skanowania historii: {e}")

    # 3. Send new message
    new_msg = await channel.send(content, view=view)
    save_pinned_message_id_for(guild_id, str(new_msg.id))
    logger.info(f"📤 [{cfg.guild_name}] Wysłano nową wiadomość {new_msg.id}")


async def update_all_rankings():
    """Zaktualizuj rankingi dla wszystkich aktywnych gildii."""
    configs = get_all_active_guild_configs()
    if configs:
        for cfg in configs:
            await update_ranking(cfg.guild_id)
    else:
        # Legacy fallback
        await update_ranking(GUILD_ID)


@tasks.loop(hours=1)
async def auto_scrape():
    logger.info("🔄 Auto-scraper uruchomiony")
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_scraper)
    await update_all_rankings()


# ── Setup command ──────────────────────────────────────────────────────────────

@bot.tree.command(name="setup_gildii", description="[ADMIN SERWERA] Skonfiguruj licznik dla tej gildii")
@app_commands.describe(
    nazwa="Wyświetlana nazwa gildii (np. SKUTA EKIPA)",
    kanal_id="ID kanału rankingowego (skopiuj z ustawień kanału)",
    rola_id="ID roli wymaganej do śledzenia (gracze gildii)",
    admin_rola_id="ID roli adminów (opcjonalne)",
    member_rola_id="ID roli członków — mogą używać /historia (opcjonalne)",
    limit="Tygodniowy limit GEMów (domyślnie 4)",
    env_klucz="Klucz env vars (np. DZIKUSY → DZIKUSY_HARD_LOGIN). Domyślnie: nazwa gildii.",
)
async def setup_gildii_command(
    interaction: discord.Interaction,
    nazwa: str,
    kanal_id: str,
    rola_id: str,
    admin_rola_id: str = "0",
    member_rola_id: str = "0",
    limit: int = 4,
    env_klucz: str = None,
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Tylko Administrator serwera może konfigurować bota.", ephemeral=True)
        return

    try:
        channel_id = int(kanal_id)
        role_id = int(rola_id)
        admin_rid = int(admin_rola_id)
        member_rid = int(member_rola_id)
    except ValueError:
        await interaction.response.send_message("❌ ID musi być liczbą. Skopiuj ID prawym klikiem na kanale/roli.", ephemeral=True)
        return

    channel = bot.get_channel(channel_id)
    if not channel:
        await interaction.response.send_message(f"❌ Nie znaleziono kanału o ID `{channel_id}`. Upewnij się, że bot ma dostęp do tego kanału.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    save_guild_config(
        guild_id=interaction.guild_id,
        guild_name=nazwa,
        ranking_channel_id=channel_id,
        role_id=role_id,
        admin_role_id=admin_rid,
        member_role_id=member_rid,
        limit=limit,
        env_key=env_klucz or nazwa,
    )
    logger.info(f"⚙️  Setup guildu {interaction.guild_id} ({nazwa}) przez {interaction.user.name}")

    # Pobierz członków + scrapuj wpłaty od razu używając kredencjałów z env vars
    import asyncio
    from scraper import get_discord_members, scrape_hard_logs, save_scrape_to_db, _creds_for_guild
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, get_discord_members, interaction.guild_id, role_id)
    creds = _creds_for_guild(env_klucz or nazwa)
    records = await loop.run_in_executor(None, scrape_hard_logs, *creds)
    if records:
        await loop.run_in_executor(None, save_scrape_to_db, records, interaction.guild_id)

    # Wyślij ranking z aktualnymi danymi
    await update_ranking(interaction.guild_id)

    embed = discord.Embed(title="✅ Gildia skonfigurowana!", color=discord.Color.green(), timestamp=datetime.now())
    embed.add_field(name="🏰 Gildia", value=f"**{nazwa}**", inline=True)
    embed.add_field(name="📢 Kanał", value=f"<#{channel_id}>", inline=True)
    embed.add_field(name="💎 Limit/tydzień", value=f"**{limit} GEM**", inline=True)
    embed.add_field(name="👥 Rola graczy", value=f"<@&{role_id}>", inline=True)
    if admin_rid:
        embed.add_field(name="🔑 Rola admin", value=f"<@&{admin_rid}>", inline=True)
    if member_rid:
        embed.add_field(name="🔹 Rola członek", value=f"<@&{member_rid}>", inline=True)
    embed.set_footer(text=f"Skonfigurował: {interaction.user.name}")
    await interaction.followup.send(embed=embed, ephemeral=True)


# ── Admin commands ─────────────────────────────────────────────────────────────

@bot.tree.command(name="wpłata_ręczna", description="[ADMIN] Dodaj ręczną wpłatę")
@app_commands.describe(
    recipient="ZA KOGO płaci (członek gildii)",
    amount="ILE diamentów",
    reason="POWÓD/Komentarz (opcjonalne)",
    payer="KTO płacił (opcjonalne)",
)
async def wpata_reczna_command(
    interaction: discord.Interaction,
    recipient: str,
    amount: int,
    reason: str = None,
    payer: str = None,
):
    try:
        if not is_admin(interaction):
            await interaction.response.send_message("❌ Tylko admini mogą dodawać ręczne wpłaty", ephemeral=True)
            return

        if amount < 1 or amount > 1000:
            await interaction.response.send_message("❌ Ilość musi być między 1 a 1000", ephemeral=True)
            return

        payer = payer.strip() if payer else None
        recipient = recipient.strip()
        if not recipient:
            await interaction.response.send_message("❌ Musisz podać nazwę odbiorcy", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        add_manual_correction(
            recipient_nick=recipient,
            amount=amount,
            date=datetime.now(),
            payer=payer,
            comment=reason,
            set_by=interaction.user.id,
            guild_id=interaction.guild_id,
        )
        logger.info(f"💳 {payer or '?'} → {recipient}: {amount}💎 ({reason})")

        await update_ranking(interaction.guild_id)

        cfg = _get_cfg(interaction.guild_id)
        embed = discord.Embed(title="✅ Wpłata ręczna dodana", color=discord.Color.green(), timestamp=datetime.now())
        embed.add_field(name="🏰 Gildia", value=f"**{cfg.guild_name}**", inline=True)
        if payer:
            embed.add_field(name="🔹 KTO", value=f"**{payer}**", inline=False)
        embed.add_field(name="🔹 ZA KOGO", value=f"**{recipient}**", inline=False)
        embed.add_field(name="🔹 ILE", value=f"**{amount} 💎**", inline=False)
        if reason:
            embed.add_field(name="🔹 POWÓD", value=f"*{reason}*", inline=False)
        embed.set_footer(text=f"Ustawił: {interaction.user.name}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"❌ Błąd wpłaty_ręcznej: {e}")
        try:
            await interaction.followup.send(f"❌ Błąd: {str(e)}", ephemeral=True)
        except Exception:
            pass


@bot.tree.command(name="ustaw_dołączenie", description="[ADMIN] Ustaw datę dołączenia członka")
@app_commands.describe(nick="Nazwa gracza", date="Data dołączenia (YYYY-MM-DD)")
async def ustaw_dolaczenie_command(interaction: discord.Interaction, nick: str, date: str):
    try:
        if not is_admin(interaction):
            await interaction.response.send_message("❌ Tylko admini mogą to ustawiać", ephemeral=True)
            return

        try:
            join_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            await interaction.response.send_message("❌ Zły format daty! Użyj: YYYY-MM-DD", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        from db_helper import update_member_join_date
        update_member_join_date(nick, join_date, guild_id=interaction.guild_id)

        embed = discord.Embed(title="✅ Data dołączenia ustawiona", color=discord.Color.blue(), timestamp=datetime.now())
        embed.add_field(name="🔹 Gracz", value=f"**{nick}**", inline=False)
        embed.add_field(name="📅 Dołączył", value=f"**{join_date.strftime('%d.%m.%Y')}**", inline=False)
        embed.set_footer(text=f"Ustawił: {interaction.user.name}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"❌ Błąd ustaw_dołączenie: {e}")
        try:
            await interaction.followup.send(f"❌ Błąd: {str(e)}", ephemeral=True)
        except Exception:
            pass


@bot.tree.command(name="tydzień_off", description="[ADMIN] Wyłącz/włącz tydzień")
@app_commands.describe(is_off="True aby wyłączyć, False aby włączyć")
async def week_off_command(interaction: discord.Interaction, is_off: bool):
    try:
        if not is_admin(interaction):
            await interaction.response.send_message("❌ Tylko admini mogą to robić", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).replace(hour=0, minute=0, second=0)
        set_week_off(week_start, is_off, guild_id=interaction.guild_id)
        status = "wyłączony" if is_off else "włączony"
        embed = discord.Embed(
            title=f"✅ Tydzień {status}",
            description=f"{week_start.strftime('%d.%m')} - {(week_start + timedelta(days=6)).strftime('%d.%m')}",
            color=discord.Color.orange()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"❌ Błąd week_off: {e}")
        try:
            await interaction.followup.send(f"❌ Błąd: {str(e)}", ephemeral=True)
        except Exception:
            pass


@bot.tree.command(name="aktualizuj", description="[ADMIN] Ręcznie zaktualizuj ranking")
async def aktualizuj_command(interaction: discord.Interaction):
    try:
        if not is_admin(interaction):
            await interaction.response.send_message("❌ Tylko admini mogą to robić", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await update_ranking(interaction.guild_id)
        cfg = _get_cfg(interaction.guild_id)
        embed = discord.Embed(title="✅ Ranking zaktualizowany", color=discord.Color.green(), timestamp=datetime.now())
        embed.add_field(name="🏰 Gildia", value=f"**{cfg.guild_name}**", inline=True)
        embed.add_field(name="📢 Kanał", value=f"<#{cfg.ranking_channel_id}>", inline=True)
        embed.set_footer(text=f"Przez: {interaction.user.name}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"❌ Błąd aktualizuj: {e}")
        await interaction.followup.send(f"❌ Błąd: {str(e)}", ephemeral=True)


@bot.tree.command(name="sync_scrape", description="[ADMIN] Ręcznie uruchom scraper")
async def sync_scrape_command(interaction: discord.Interaction):
    try:
        if not is_admin(interaction):
            await interaction.response.send_message("❌ Tylko admini mogą to robić", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        msg = await interaction.followup.send(
            embed=discord.Embed(title="🔄 Scraper uruchomiony", description="Czekaj...", color=discord.Color.blue()),
            ephemeral=True,
            wait=True
        )

        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_scraper)
        await update_all_rankings()

        cfg = _get_cfg(interaction.guild_id)
        done_embed = discord.Embed(title="✅ Scraper ukończony", color=discord.Color.green(), timestamp=datetime.now())
        done_embed.add_field(name="🏰 Gildia", value=f"**{cfg.guild_name}**", inline=True)
        done_embed.add_field(name="📢 Kanał", value=f"<#{cfg.ranking_channel_id}>", inline=True)
        await msg.edit(embed=done_embed)
        await asyncio.sleep(60)
        await msg.delete()

    except Exception as e:
        logger.error(f"❌ Błąd sync_scrape: {e}")
        await interaction.followup.send(f"❌ Błąd: {str(e)}")


# ── Member commands ────────────────────────────────────────────────────────────

@bot.tree.command(name="historia", description="Pokaż historię wpłat dla gracza")
@app_commands.describe(nick="Nick gracza (z gry lub Discord)")
async def historia_command(interaction: discord.Interaction, nick: str):
    try:
        if not is_member(interaction):
            await interaction.response.send_message("❌ Tylko członkowie gildii mogą używać tej komendy", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        data = get_all_logs_for_nick(nick.strip(), guild_id=interaction.guild_id)
        if not data:
            await interaction.followup.send(f"❌ Nie znaleziono gracza: **{nick}**", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📜 Historia wpłat: {data['discord_nick']}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )

        if data['corrections']:
            lines = []
            for c in data['corrections']:
                line = f"`{c['week_start'].strftime('%d.%m')}` **+{int(c['amount'])}💎**"
                if c['payer']:
                    line += f" od {c['payer']}"
                if c['comment']:
                    line += f" — *{c['comment']}*"
                lines.append(line)
            embed.add_field(
                name=f"✍️ Wpłaty ręczne ({len(data['corrections'])})",
                value="\n".join(lines[:20]) + ("…" if len(lines) > 20 else ""),
                inline=False
            )
        else:
            embed.add_field(name="✍️ Wpłaty ręczne", value="*Brak*", inline=False)

        if data['payments']:
            from collections import defaultdict
            by_week = defaultdict(float)
            for p in data['payments']:
                by_week[p['week_start']] += p['amount']
            lines = [
                f"`{ws.strftime('%d.%m.%Y')}` **{int(total)}💎**"
                for ws, total in sorted(by_week.items(), reverse=True)
            ]
            embed.add_field(
                name=f"🎮 Wpłaty z gry ({len(by_week)} tygodni, łącznie {int(sum(by_week.values()))}💎)",
                value="\n".join(lines[:20]) + ("…" if len(lines) > 20 else ""),
                inline=False
            )
        else:
            embed.add_field(name="🎮 Wpłaty z gry", value="*Brak*", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"❌ Błąd historia: {e}")
        try:
            await interaction.followup.send(f"❌ Błąd: {str(e)}", ephemeral=True)
        except Exception:
            pass


@bot.tree.command(name="members", description="Lista wszystkich członków")
async def members_command(interaction: discord.Interaction):
    try:
        if not is_member(interaction):
            await interaction.response.send_message("❌ Tylko członkowie gildii mogą używać tej komendy", ephemeral=True)
            return
        members = get_all_active_members(guild_id=interaction.guild_id)
        embed = discord.Embed(
            title="📋 Członkowie gildii",
            description="\n".join(sorted(members)),
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Razem: {len(members)} członków")
        await interaction.response.send_message(embed=embed)

    except Exception as e:
        logger.error(f"❌ Błąd members: {e}")
        await interaction.response.send_message(f"❌ Błąd: {str(e)}", ephemeral=True)


@bot.tree.command(name="zaległości", description="Ręczne wpłaty w tym tygodniu")
@app_commands.describe(member="Nazwa członka (opcjonalnie)")
async def zaleglosci_command(interaction: discord.Interaction, member: str = None):
    try:
        if not is_member(interaction):
            await interaction.response.send_message("❌ Tylko członkowie gildii mogą używać tej komendy", ephemeral=True)
            return
        week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).replace(hour=0, minute=0, second=0)
        corrections = get_corrections_for_week(week_start, guild_id=interaction.guild_id)

        if member:
            if member in corrections:
                embed = discord.Embed(title=f"Wpłaty: {member}", color=discord.Color.blue())
                for corr in corrections[member]:
                    text = f"{corr.amount}💎"
                    if corr.comment:
                        text += f" - {corr.comment}"
                    embed.add_field(name=corr.date.strftime("%d.%m %H:%M"), value=text, inline=False)
            else:
                embed = discord.Embed(title=f"Wpłaty: {member}", description="Brak wpisów", color=discord.Color.greyple())
        else:
            embed = discord.Embed(title="Ręczne wpłaty w tym tygodniu", color=discord.Color.blue(), timestamp=datetime.now())
            if corrections:
                for m, corrs in sorted(corrections.items())[:10]:
                    total = sum(c.amount for c in corrs)
                    embed.add_field(name=m, value=f"{total}💎 ({len(corrs)} wpłat)", inline=True)
            else:
                embed.description = "Brak ręcznych wpłat"

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        logger.error(f"❌ Błąd zaległości: {e}")
        await interaction.response.send_message(f"❌ Błąd: {str(e)}", ephemeral=True)


@bot.tree.command(name="lista_wpłat", description="[ADMIN] Pokaż ręczne wpłaty gracza z ID")
@app_commands.describe(nick="Nick gracza")
async def lista_wplat_command(interaction: discord.Interaction, nick: str):
    try:
        if not is_admin(interaction):
            await interaction.response.send_message("❌ Tylko admini mogą to robić", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        corrections = get_corrections_for_nick(nick.strip(), guild_id=interaction.guild_id)

        if not corrections:
            await interaction.followup.send(f"❌ Brak ręcznych wpłat dla: **{nick}**", ephemeral=True)
            return

        lines = []
        for c in corrections:
            line = f"`ID:{c['id']}` `{c['week_start'].strftime('%d.%m')}` **+{int(c['amount'])}💎**"
            if c['payer']:
                line += f" od {c['payer']}"
            if c['comment']:
                line += f" — *{c['comment']}*"
            lines.append(line)

        embed = discord.Embed(
            title=f"✍️ Wpłaty ręczne: {nick}",
            description="\n".join(lines),
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.set_footer(text="Użyj /usuń_wpłatę <ID> lub /edytuj_wpłatę <ID>")
        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"❌ Błąd lista_wpłat: {e}")
        try:
            await interaction.followup.send(f"❌ Błąd: {str(e)}", ephemeral=True)
        except Exception:
            pass


@bot.tree.command(name="usuń_wpłatę", description="[ADMIN] Usuń ręczną wpłatę po ID")
@app_commands.describe(id="ID wpłaty (widoczne w /lista_wpłat)")
async def usun_wplate_command(interaction: discord.Interaction, id: int):
    try:
        if not is_admin(interaction):
            await interaction.response.send_message("❌ Tylko admini mogą to robić", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        ok = delete_correction(id, guild_id=interaction.guild_id)
        if not ok:
            await interaction.followup.send(f"❌ Nie znaleziono wpłaty o ID: **{id}**", ephemeral=True)
            return

        await update_ranking(interaction.guild_id)
        await interaction.followup.send(f"✅ Usunięto wpłatę ID:{id} i zaktualizowano ranking.", ephemeral=True)

    except Exception as e:
        logger.error(f"❌ Błąd usuń_wpłatę: {e}")
        try:
            await interaction.followup.send(f"❌ Błąd: {str(e)}", ephemeral=True)
        except Exception:
            pass


@bot.tree.command(name="edytuj_wpłatę", description="[ADMIN] Edytuj kwotę lub komentarz ręcznej wpłaty")
@app_commands.describe(
    id="ID wpłaty",
    kwota="Nowa kwota (zostaw puste aby nie zmieniać)",
    komentarz="Nowy komentarz (wpisz '-' aby usunąć)",
)
async def edytuj_wplate_command(interaction: discord.Interaction, id: int, kwota: int = None, komentarz: str = None):
    try:
        if not is_admin(interaction):
            await interaction.response.send_message("❌ Tylko admini mogą to robić", ephemeral=True)
            return

        if kwota is None and komentarz is None:
            await interaction.response.send_message("❌ Podaj kwotę lub komentarz do zmiany", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        new_comment = None if komentarz == "-" else komentarz
        ok = update_correction(id, amount=kwota, comment=new_comment if komentarz is not None else None)
        if not ok:
            await interaction.followup.send(f"❌ Nie znaleziono wpłaty o ID: **{id}**", ephemeral=True)
            return

        await update_ranking(interaction.guild_id)

        changes = []
        if kwota is not None:
            changes.append(f"kwota → **{kwota}💎**")
        if komentarz is not None:
            changes.append(f"komentarz → *{new_comment or '(usunięty)'}*")

        await interaction.followup.send(f"✅ Zaktualizowano wpłatę ID:{id}: {', '.join(changes)}", ephemeral=True)

    except Exception as e:
        logger.error(f"❌ Błąd edytuj_wpłatę: {e}")
        try:
            await interaction.followup.send(f"❌ Błąd: {str(e)}", ephemeral=True)
        except Exception:
            pass


def run_bot():
    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    run_bot()
