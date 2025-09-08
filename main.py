
import discord
from discord.ext import commands
from discord import ui
import asyncio
import os
from dotenv import load_dotenv
import sqlite3

# --- Your Seller Information (Edit Here) ---
SELLER_INFO = {
    "name": "Tuấn Thảo Real",
    "contact_fb": "https://www.facebook.com/tuanthaoreal",
    "contact_zalo": "https://zalo.me/0367361316",
    "avatar_url": "https://i.postimg.cc/FspLSTJc/avatar.png"  # URL to your avatar image
}

# --- Database Setup & Functions ---
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    # Changed 'album' to 'description'
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        description TEXT NOT NULL,
        image_url TEXT NOT NULL,
        price INTEGER NOT NULL
    )
    """)
    conn.commit()
    conn.close()

def get_product_by_code(code):
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE lower(code) = ?", (code.lower(),))
    product = cursor.fetchone()
    conn.close()
    return dict(product) if product else None

def get_new_product_code():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT code FROM products ORDER BY id DESC LIMIT 1")
    last_code = cursor.fetchone()
    conn.close()
    if not last_code or not last_code[0]:
        return "P001"
    last_num = int(last_code[0][1:])
    return f"P{last_num + 1:03d}"

# --- Data Loading ---
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

price_map = {
    "1": ("100.000₫ → 500.000₫", 100_000, 500_000),
    "2": ("500.000₫ → 1.000.000₫", 500_001, 1_000_000),
    "3": ("1.000.000₫ → 3.000.000₫", 1_000_001, 3_000_000),
    "4": ("Trên 3.000.000₫", 3_000_001, float('inf')),
}

# --- Bot & UI Components ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- CUSTOMER UI VIEWS ---
class ProductInfoView(ui.View):
    # Removed the 'Full Album' button
    def __init__(self, product):
        super().__init__(timeout=None)
        self.add_item(ui.Button(label="💬 Facebook", style=discord.ButtonStyle.link, url=SELLER_INFO['contact_fb']))
        self.add_item(ui.Button(label="💬 Zalo", style=discord.ButtonStyle.link, url=SELLER_INFO['contact_zalo']))

class ProductSelectionView(ui.View):
    def __init__(self, matched_products):
        super().__init__(timeout=300)
        for product in matched_products:
            self.add_item(ProductButton(product['code']))

class ProductButton(ui.Button):
    def __init__(self, code):
        super().__init__(label=code, style=discord.ButtonStyle.secondary, custom_id=f"product_{code}")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        product = get_product_by_code(self.label)
        if not product:
            return await interaction.followup.send("Lỗi: Không tìm thấy sản phẩm này.", ephemeral=True)
        
        # Updated embed to show description
        embed = discord.Embed(title=f"Thông tin sản phẩm: `{product['code']}`", description=product['description'], color=0x6A0DAD)
        embed.set_author(name=f"Cung cấp bởi: {SELLER_INFO['name']}", icon_url=SELLER_INFO['avatar_url'])
        embed.set_image(url=product['image_url'])

        await interaction.followup.send(embed=embed, view=ProductInfoView(product), ephemeral=True)

class PriceRangeView(ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        for key, (label, _, _) in price_map.items():
            self.add_item(PriceButton(key, label))

class PriceButton(ui.Button):
    def __init__(self, price_key, label):
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"price_{price_key}")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        _, min_p, max_p = price_map[self.custom_id.split('_')[1]]
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT code FROM products WHERE price >= ? AND price <= ?", (min_p, max_p))
        matched = cursor.fetchall()
        conn.close()
        if not matched:
            return await interaction.followup.send("😥 Rất tiếc, không có sản phẩm nào trong khoảng giá này.", ephemeral=True)
        await interaction.followup.send(f"🔎 Tìm thấy {len(matched)} sản phẩm. Vui lòng chọn một mã:", view=ProductSelectionView(matched), ephemeral=True)

class StartView(ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @ui.button(label="Bắt đầu xem sản phẩm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(embed=discord.Embed(title="🌸 Vui lòng chọn khoảng giá 🌸", color=0xFF69B4), view=PriceRangeView(), ephemeral=True)
        self.stop()

    @ui.button(label="Không, cảm ơn", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("👍 OK, mình ở đây nếu bạn cần hỗ trợ.", ephemeral=True)
        self.stop()

# --- Bot Events & Customer Commands ---
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

@bot.command()
async def hi(ctx):
    await ctx.send(embed=discord.Embed(title="👋 Xin chào! Mình là Bot Hỗ Trợ.", description="Bạn có muốn bắt đầu tìm sản phẩm không?", color=0x00FFAA), view=StartView())

# --- ADMIN COMMANDS ---
@bot.group()
@commands.is_owner()
async def admin(ctx):
    if ctx.invoked_subcommand is None:
        await ctx.send('Lệnh admin không hợp lệ. Thử `!admin add`, `!admin del <code>`, hoặc `!admin list`.', ephemeral=True)

@admin.error
async def admin_error(ctx, error):
    if isinstance(error, commands.NotOwner):
        await ctx.send("⛔ Bạn không có quyền sử dụng lệnh này.", ephemeral=True)
    else:
        await ctx.send(f"Đã có lỗi xảy ra: {error}", ephemeral=True)

@admin.command(name='add')
async def add_product(ctx):
    def check(m):
        return isinstance(m.channel, discord.DMChannel) and m.author == ctx.author

    try:
        await ctx.author.send("**Bắt đầu thêm sản phẩm mới...**\n\n**(1/3)** Vui lòng gửi **thông tin/mô tả** cho sản phẩm:")
        desc_msg = await bot.wait_for('message', check=check, timeout=300)
        description = desc_msg.content

        await ctx.author.send("**(2/3)** Vui lòng gửi **link ảnh đại diện (image URL)** của sản phẩm:")
        image_msg = await bot.wait_for('message', check=check, timeout=300)
        image_url = image_msg.content

        await ctx.author.send("**(3/3)** Vui lòng gửi **giá bán** của sản phẩm (chỉ nhập số, ví dụ: `1500000`):")
        price_msg = await bot.wait_for('message', check=check, timeout=300)
        price = int(price_msg.content)

        new_code = get_new_product_code()
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO products (code, description, image_url, price) VALUES (?, ?, ?, ?)", (new_code, description, image_url, price))
        conn.commit()
        conn.close()

        embed = discord.Embed(title="✅ Thêm sản phẩm thành công!", color=0x00FF00)
        embed.add_field(name="Mã sản phẩm", value=new_code, inline=False)
        embed.add_field(name="Giá bán", value=f"{price:,}₫", inline=False)
        embed.add_field(name="Mô tả", value=description[:1024], inline=False) # Show first 1024 chars of description
        embed.set_image(url=image_url)
        await ctx.author.send(embed=embed)

    except asyncio.TimeoutError:
        await ctx.author.send("⌛ Hết thời gian. Vui lòng gõ `!admin add` để thử lại.")
    except ValueError:
        await ctx.author.send("❌ Giá tiền không hợp lệ. Vui lòng nhập một con số. Thử lại với `!admin add`.")
    except Exception as e:
        await ctx.author.send(f"Đã có lỗi xảy ra: {e}")

@admin.command(name='del')
async def delete_product(ctx, code: str):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE lower(code) = ?", (code.lower(),))
    changes = conn.total_changes
    conn.commit()
    conn.close()

    if changes > 0:
        await ctx.send(f"🗑️ Đã xóa thành công sản phẩm có mã `{code}`.", ephemeral=True)
    else:
        await ctx.send(f"⚠️ Không tìm thấy sản phẩm nào có mã `{code}`.", ephemeral=True)

@admin.command(name='list')
async def list_products(ctx):
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT code, price, description FROM products ORDER BY id")
    products = cursor.fetchall()
    conn.close()

    if not products:
        return await ctx.send("📭 Database trống, chưa có sản phẩm nào.", ephemeral=True)

    # Paginate list if it's too long
    pages = []
    current_page = ""
    for p in products:
        line = f"**- `{p['code']}`**: {p['price']:,}₫\n*Mô tả: {p['description'][:70]}...*\n\n"
        if len(current_page) + len(line) > 1000:
            pages.append(current_page)
            current_page = ""
        current_page += line
    pages.append(current_page)

    for i, page_content in enumerate(pages):
        embed = discord.Embed(title=f"📦 Danh sách sản phẩm ({len(products)}) - Trang {i+1}/{len(pages)}", description=page_content, color=0x3498db)
        await ctx.send(embed=embed, ephemeral=True)

# --- Main Execution Logic ---
async def main():
    # Reset database on start for development to apply schema changes
    if os.path.exists('database.db'):
        os.remove('database.db')
        print("Old database removed to apply new schema.")
    
    init_db()
    print("Database initialized.")
    
    if DISCORD_TOKEN:
        async with bot:
            print("Starting bot...")
            await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot shutdown gracefully.")

