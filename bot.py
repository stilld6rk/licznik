import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
from config import DISCORD_BOT_TOKEN, GUILD_ID, ROLE_ID, GOLD, ORANGE, RED, GREEN, RANKING_CHANNEL_ID
from db_helper import (
    get_or_create_member, add_manual_correction, get_all_active_members,
    is_week_off, set_week_off, delete_correction, get_corrections_for_week
)
from calculator import run_week_calc_and_send, build_ranking_content
from db_helper import get_pinned_message_id, save_pinned_message_id
from scraper import run_scraper
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    logger.info(f"✅ Bot zalogowany jako {bot.user}")
    try:
        await bot.tree.sync()
        logger.info("✅ Slash commands zsynchronizowane")
    except Exception as e:
        logger.error(f"❌ Błąd synchronizacji: {e}")

    if not auto_scrape.is_running():
        auto_scrape.start()
    if not daily_ranking_update.is_running():
        daily_ranking_update.start()


async def update_ranking():
    """Wyślij lub edytuj przypiętą wiadomość rankingową przez bota"""
    channel = bot.get_channel(RANKING_CHANNEL_ID)
    if not channel:
        logger.error(f"❌ Nie znaleziono kanału {RANKING_CHANNEL_ID}")
        return

    content = build_ranking_content()
    msg_id = get_pinned_message_id()

    if msg_id:
        try:
            msg = await channel.fetch_message(int(msg_id))
            await msg.edit(content=content)
            logger.info(f"✏️  Zaktualizowano wiadomość {msg_id}")
            return
        except discord.NotFound:
            logger.warning("⚠️  Stara wiadomość usunięta, tworzę nową")
            save_pinned_message_id(None)

    new_msg = await channel.send(content)
    save_pinned_message_id(str(new_msg.id))
    logger.info(f"📤 Wysłano nową wiadomość {new_msg.id}")


@tasks.loop(hours=1)
async def auto_scrape():
    """Co godzinę scrapuj dane"""
    logger.info("🔄 Auto-scraper uruchomiony")
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_scraper)


@tasks.loop(hours=24)
async def daily_ranking_update():
    """Co 24h aktualizuj przypiętą wiadomość rankingową"""
    logger.info("📊 Dzienna aktualizacja rankingu")
    await update_ranking()


@bot.tree.command(name="wpłata_ręczna", description="Dodaj ręczną wpłatę: KTO → ZA KOGO, ILE, POWÓD")
@app_commands.describe(
    payer="🔹 KTO płacił (np. ADMIN)",
    recipient="🔹 ZA KOGO płaci (członek gildii)",
    amount="🔹 ILE diamentów",
    reason="🔹 POWÓD/Komentarz (np. zastępstwo)"
)
async def wpata_reczna_command(
    interaction: discord.Interaction,
    payer: str,
    recipient: str,
    amount: int,
    reason: str = None
):
    """
    Dodaj ręczną wpłatę w formacie:
    KTO → ZA KOGO, ILE 💎, POWÓD
    """
    try:
        # Sprawdzenie uprawnień (admin)
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Tylko admini mogą dodawać ręczne wpłaty",
                ephemeral=True
            )
            return
        
        # Sprawdzenie ilości
        if amount < 1 or amount > 10:
            await interaction.response.send_message(
                "❌ Ilość musi być między 1 a 10 💎",
                ephemeral=True
            )
            return
        
        # Sanitize nicknames
        payer = payer.strip()
        recipient = recipient.strip()
        
        if not recipient:
            await interaction.response.send_message(
                "❌ Musisz podać nazwę odbiorcy",
                ephemeral=True
            )
            return
        
        # Dodaj wpłatę
        add_manual_correction(
            recipient_nick=recipient,
            amount=amount,
            date=datetime.now(),
            payer=payer if payer else None,
            comment=reason,
            set_by=interaction.user.id
        )
        
        logger.info(f"💳 {payer} → {recipient}: {amount}💎 ({reason})")
        
        await update_ranking()
        
        # Embed potwierdzenia
        embed = discord.Embed(
            title="✅ Wpłata ręczna dodana",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(
            name="🔹 KTO", 
            value=f"**{payer}**", 
            inline=False
        )
        embed.add_field(
            name="🔹 ZA KOGO", 
            value=f"**{recipient}**", 
            inline=False
        )
        embed.add_field(
            name="🔹 ILE", 
            value=f"**{amount} 💎**", 
            inline=False
        )
        if reason:
            embed.add_field(
                name="🔹 POWÓD", 
                value=f"*{reason}*", 
                inline=False
            )
        embed.set_footer(text=f"Ustawił: {interaction.user.name}")
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f"❌ Błąd komendy wpłaty_ręcznej: {e}")
        await interaction.response.send_message(
            f"❌ Błąd: {str(e)}",
            ephemeral=True
        )


@bot.tree.command(name="ustaw_dołączenie", description="[ADMIN] Ustaw datę dołączenia członka")
@app_commands.describe(
    nick="Nazwa gracza",
    date="Data dołączenia (format: YYYY-MM-DD, np. 2024-01-15)"
)
async def ustaw_dolaczenie_command(
    interaction: discord.Interaction,
    nick: str,
    date: str
):
    """
    Ustaw datę kiedy gracz dołączył do gildii.
    Wpłaty będą liczone od tego tygodnia.
    """
    try:
        # Sprawdzenie uprawnień
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Tylko admini mogą to ustawiać",
                ephemeral=True
            )
            return
        
        # Parse daty
        try:
            join_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            await interaction.response.send_message(
                "❌ Zły format daty! Użyj: YYYY-MM-DD (np. 2024-01-15)",
                ephemeral=True
            )
            return
        
        # Ustaw datę
        from db_helper import update_member_join_date
        update_member_join_date(nick, join_date)
        
        logger.info(f"📅 {nick} dołączył: {join_date.strftime('%d.%m.%Y')}")
        
        embed = discord.Embed(
            title="✅ Data dołączenia ustawiona",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.add_field(name="🔹 Gracz", value=f"**{nick}**", inline=False)
        embed.add_field(name="📅 Dołączył", value=f"**{join_date.strftime('%d.%m.%Y')}**", inline=False)
        embed.add_field(
            name="ℹ️ Info", 
            value="Wpłaty będą liczone od tego tygodnia", 
            inline=False
        )
        embed.set_footer(text=f"Ustawił: {interaction.user.name}")
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f"❌ Błąd ustaw_dołączenie: {e}")
        await interaction.response.send_message(
            f"❌ Błąd: {str(e)}",
            ephemeral=True
        )


@bot.tree.command(name="info_członka", description="Pokaż informacje o członku (data dołączenia, wpłaty)")
@app_commands.describe(
    nick="Nazwa gracza"
)
async def info_czlonka_command(
    interaction: discord.Interaction,
    nick: str
):
    """Pokaż informacje o członku"""
    try:
        from database import get_session, GuildMember
        
        session = get_session()
        member = session.query(GuildMember).filter_by(nick=nick).first()
        session.close()
        
        if not member:
            await interaction.response.send_message(
                f"❌ Nie znaleziono gracza: **{nick}**",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=f"📋 Informacje o: {nick}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.add_field(name="🔹 Nick", value=f"**{member.nick}**", inline=False)
        
        if member.discord_id:
            embed.add_field(name="🆔 Discord ID", value=f"`{member.discord_id}`", inline=False)
        
        if member.join_date:
            embed.add_field(
                name="📅 Dołączył", 
                value=f"**{member.join_date.strftime('%d.%m.%Y')}**",
                inline=False
            )
        else:
            embed.add_field(
                name="📅 Dołączył", 
                value="❓ *Brak daty* (ustaw komendą `/ustaw_dołączenie`)",
                inline=False
            )
        
        status = "✅ Aktywny" if member.is_active else "❌ Nieaktywny"
        embed.add_field(name="Status", value=status, inline=False)
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f"❌ Błąd info_czlonka: {e}")
        await interaction.response.send_message(
            f"❌ Błąd: {str(e)}",
            ephemeral=True
        )


@bot.tree.command(name="zaległości", description="Pokaż zaległości dla członka w tym tygodniu")
@app_commands.describe(member="Nazwa członka (opcjonalnie)")
async def zaleglosci_command(interaction: discord.Interaction, member: str = None):
    """Pokaż zaległości"""
    try:
        week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).replace(hour=0, minute=0, second=0)
        
        if member:
            # Pokaż dla konkretnego członka
            corrections = get_corrections_for_week(week_start)
            if member in corrections:
                embed = discord.Embed(
                    title=f"Wpłaty: {member}",
                    color=discord.Color.blue()
                )
                for corr in corrections[member]:
                    text = f"{corr.amount}💎"
                    if corr.comment:
                        text += f" - {corr.comment}"
                    embed.add_field(
                        name=corr.date.strftime("%d.%m %H:%M"),
                        value=text,
                        inline=False
                    )
            else:
                embed = discord.Embed(
                    title=f"Wpłaty: {member}",
                    description="Brak wpisów",
                    color=discord.Color.greyple()
                )
        else:
            # Pokaż krótkie podsumowanie
            all_members = get_all_active_members()
            corrections = get_corrections_for_week(week_start)
            
            embed = discord.Embed(
                title="Ręczne wpłaty w tym tygodniu",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            if corrections:
                for member, corrs in sorted(corrections.items())[:10]:
                    total = sum(c.amount for c in corrs)
                    embed.add_field(
                        name=member,
                        value=f"{total}💎 ({len(corrs)} wpłat)",
                        inline=True
                    )
            else:
                embed.description = "Brak ręcznych wpłat"
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f"❌ Błąd komendy zaległości: {e}")
        await interaction.response.send_message(
            f"❌ Błąd: {str(e)}",
            ephemeral=True
        )


@bot.tree.command(name="tydzień_off", description="Wyłącz/włącz tydzień (nie wysyła rankingu)")
@app_commands.describe(is_off="True aby wyłączyć, False aby włączyć")
async def week_off_command(interaction: discord.Interaction, is_off: bool):
    """Ustaw tydzień jako wyłączony"""
    try:
        # Sprawdzenie uprawnień
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Tylko admini mogą to robić",
                ephemeral=True
            )
            return
        
        week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).replace(hour=0, minute=0, second=0)
        set_week_off(week_start, is_off)
        
        status = "wyłączony" if is_off else "włączony"
        embed = discord.Embed(
            title=f"✅ Tydzień {status}",
            description=f"{week_start.strftime('%d.%m')} - {(week_start + timedelta(days=6)).strftime('%d.%m')}",
            color=discord.Color.orange()
        )
        
        await interaction.response.send_message(embed=embed)
        logger.info(f"⏭️  Tydzień ustawiony na {status}")
        
    except Exception as e:
        logger.error(f"❌ Błąd komendy week_off: {e}")
        await interaction.response.send_message(
            f"❌ Błąd: {str(e)}",
            ephemeral=True
        )


@bot.tree.command(name="init_ranking", description="[ADMIN] Wyślij ranking po raz pierwszy na kanał")
async def init_ranking_command(interaction: discord.Interaction):
    """Wyślij pierwszą wiadomość rankingową (lub zastąp istniejącą)"""
    try:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Tylko admini mogą to robić", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        save_pinned_message_id(None)
        await update_ranking()
        await interaction.followup.send("✅ Ranking wysłany na kanał webhooka!", ephemeral=True)
        logger.info(f"📌 Init ranking przez {interaction.user.name}")

    except Exception as e:
        logger.error(f"❌ Błąd init_ranking: {e}")
        await interaction.followup.send(f"❌ Błąd: {str(e)}", ephemeral=True)


@bot.tree.command(name="aktualizuj", description="[ADMIN] Ręcznie zaktualizuj przypiętą wiadomość rankingową")
async def aktualizuj_command(interaction: discord.Interaction):
    """Ręczna aktualizacja przypiętej wiadomości rankingowej"""
    try:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Tylko admini mogą to robić",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        await update_ranking()
        await interaction.followup.send("✅ Ranking zaktualizowany!", ephemeral=True)
        logger.info(f"📊 Ręczna aktualizacja przez {interaction.user.name}")

    except Exception as e:
        logger.error(f"❌ Błąd aktualizuj: {e}")
        await interaction.followup.send(f"❌ Błąd: {str(e)}", ephemeral=True)


@bot.tree.command(name="sync_scrape", description="Ręcznie uruchom scraper (admin)")
async def sync_scrape_command(interaction: discord.Interaction):
    """Ręczne uruchomienie scrapera"""
    try:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Tylko admini mogą to robić",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        
        embed = discord.Embed(
            title="🔄 Scraper uruchomiony",
            description="Czekaj...",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed)
        
        run_scraper()
        await update_ranking()

        embed = discord.Embed(
            title="✅ Scraper ukończony i ranking zaktualizowany",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed)
        logger.info("✅ Ręczny scraper uruchomiony")
        
    except Exception as e:
        logger.error(f"❌ Błąd sync_scrape: {e}")
        await interaction.followup.send(f"❌ Błąd: {str(e)}")


@bot.tree.command(name="members", description="Lista wszystkich członków")
async def members_command(interaction: discord.Interaction):
    """Pokaż listę członków"""
    try:
        members = get_all_active_members()
        
        embed = discord.Embed(
            title="📋 Członkowie gildii",
            description="\n".join(sorted(members)),
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Razem: {len(members)} członków")
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        logger.error(f"❌ Błąd members: {e}")
        await interaction.response.send_message(
            f"❌ Błąd: {str(e)}",
            ephemeral=True
        )


def run_bot():
    """Uruchom bota"""
    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    run_bot()
