import asyncio
import json
import os

import discord
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN")  # set this as an environment variable
CATEGORY_NAME = "user logs"
DATA_FILE = "data.json"

intents = discord.Intents.default()
intents.members = True  # also enable "Server Members Intent" in the Dev Portal


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


class Bot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.data = load_data()

    async def setup_hook(self):
        await self.tree.sync()


bot = Bot()


async def ensure_channels(guild: discord.Guild):
    """Create the 'user logs' category + welcome/goodbye channels if missing."""
    category = discord.utils.find(
        lambda c: c.name.lower() == CATEGORY_NAME, guild.categories
    )
    if category is None:
        category = await guild.create_category(CATEGORY_NAME)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(send_messages=False),
        guild.me: discord.PermissionOverwrite(send_messages=True, embed_links=True),
    }

    ids = {}
    for name in ("welcome", "goodbye"):
        channel = discord.utils.get(category.text_channels, name=name)
        if channel is None:
            channel = await guild.create_text_channel(
                name, category=category, overwrites=overwrites
            )
        ids[name] = channel.id

    bot.data[str(guild.id)] = ids
    save_data(bot.data)
    return ids


def get_channel(guild: discord.Guild, key: str):
    ids = bot.data.get(str(guild.id))
    return guild.get_channel(ids[key]) if ids else None


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.event
async def on_guild_join(guild: discord.Guild):
    try:
        await ensure_channels(guild)
    except discord.Forbidden:
        print(f"Missing permissions to create channels in {guild.name}")


@bot.event
async def on_member_join(member: discord.Member):
    channel = get_channel(member.guild, "welcome")
    if channel:
        embed = discord.Embed(
            title="Welcome!",
            description=f"{member.mention} just joined **{member.guild.name}** 🎉\n"
            f"You are member #{member.guild.member_count}.",
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)


@bot.event
async def on_member_remove(member: discord.Member):
    channel = get_channel(member.guild, "goodbye")
    if channel:
        embed = discord.Embed(
            title="Goodbye",
            description=f"**{member}** left **{member.guild.name}** 👋",
            color=discord.Color.red(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)


@bot.tree.command(name="setup", description="Create the user logs category with welcome & goodbye channels")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.guild_only()
async def setup(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await ensure_channels(interaction.guild)
    await interaction.followup.send("✅ Done! 'user logs' category is ready.", ephemeral=True)


@bot.tree.command(name="nickall", description="Add a prefix or suffix to every member's nickname")
@app_commands.describe(
    mode="Add the text before (prefix) or after (suffix) the name",
    text="Text to add, e.g. [RL] or ✨",
    include_bots="Also rename bots (default: no)",
)
@app_commands.choices(
    mode=[
        app_commands.Choice(name="Prefix", value="prefix"),
        app_commands.Choice(name="Suffix", value="suffix"),
    ]
)
@app_commands.checks.has_permissions(manage_nicknames=True)
@app_commands.guild_only()
async def nickall(
    interaction: discord.Interaction,
    mode: app_commands.Choice[str],
    text: app_commands.Range[str, 1, 20],
    include_bots: bool = False,
):
    await interaction.response.send_message("⏳ Changing nicknames, please wait...", ephemeral=True)
    guild = interaction.guild
    done = skipped = 0

    for member in guild.members:
        if member.bot and not include_bots:
            continue
        if member == guild.owner or member.top_role >= guild.me.top_role:
            skipped += 1
            continue

        base = member.display_name
        # don't add the same prefix/suffix twice
        if (mode.value == "prefix" and base.startswith(text + " ")) or (
            mode.value == "suffix" and base.endswith(" " + text)
        ):
            skipped += 1
            continue

        # keep within Discord's 32 character nickname limit
        room = 32 - len(text) - 1
        base = base[:room]
        new_nick = f"{text} {base}" if mode.value == "prefix" else f"{base} {text}"
        try:
            await member.edit(nick=new_nick, reason=f"/nickall by {interaction.user}")
            done += 1
        except (discord.Forbidden, discord.HTTPException):
            skipped += 1
        await asyncio.sleep(1)  # avoid rate limits

    await interaction.channel.send(
        f"{interaction.user.mention} ✅ Nicknames changed: **{done}** | Skipped: **{skipped}**"
    )


@bot.tree.command(name="nickreset", description="Reset every member's nickname")
@app_commands.checks.has_permissions(manage_nicknames=True)
@app_commands.guild_only()
async def nickreset(interaction: discord.Interaction):
    await interaction.response.send_message("⏳ Resetting nicknames...", ephemeral=True)
    guild = interaction.guild
    done = 0
    for member in guild.members:
        if member == guild.owner or member.top_role >= guild.me.top_role or member.nick is None:
            continue
        try:
            await member.edit(nick=None, reason=f"/nickreset by {interaction.user}")
            done += 1
        except (discord.Forbidden, discord.HTTPException):
            pass
        await asyncio.sleep(1)
    await interaction.channel.send(f"{interaction.user.mention} ✅ Reset **{done}** nicknames.")


bot.run(TOKEN)
