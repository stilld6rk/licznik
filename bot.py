import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
from config import DISCORD_BOT_TOKEN, GUILD_ID, ROLE_ID, GOLD, ORANGE, RED, GREEN
from db_helper import (
    get_or_create_member, add_manual_correction, get_all_active_members,
    is_week_off, set_week_off, delete_correction, get_corrections_for_week
)
from calculator import run_week_calc_and_send
from scraper import run_scraper
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Intent i command prefix
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
    
    # Uruchom scheduled tasks
    if not auto_scrape.is_running():
        auto_scrape.start()


@tasks.loop(hours=1)
async def auto_scrape():
    """Co godzinę scrapuj dane"""
    logger.info("🔄 Auto-scraper uruchomiony")
    run_scraper()


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
        
        # Zaktualizuj ranking
        week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).replace(hour=0, minute=0, second=0)
        run_week_calc_and_send(week_start)
        
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
        
        # Zaktualizuj rankingi
        from db_helper import get_all_weeks
        weeks = get_all_weeks()
        for week_start in weeks[-4:]:  # Ostatnie 4 tygodnie
            run_week_calc_and_send(week_start)
        
        embed = discord.Embed(
            title="✅ Scraper ukończony",
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
