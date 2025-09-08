
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
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        description TEXT NOT NULL,
        image_urls TEXT NOT NULL,
        price INTEGER NOT NULL,
        shop_url TEXT
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
class ProductGalleryView(ui.View):
    def __init__(self, product):
        super().__init__(timeout=300)
        self.product = product
        self.image_urls = product['image_urls'].split()
        self.current_page = 0

        self.update_buttons()
        # Add Shop, Facebook, and Zalo buttons
        if self.product['shop_url']:
            self.add_item(ui.Button(label="🛒 Mua ngay", style=discord.ButtonStyle.success, url=self.product['shop_url'], row=1))
        self.add_item(ui.Button(label="💬 Facebook", style=discord.ButtonStyle.link, url=SELLER_INFO['contact_fb'], row=1))
        self.add_item(ui.Button(label="💬 Zalo", style=discord.ButtonStyle.link, url=SELLER_INFO['contact_zalo'], row=1))

    def update_buttons(self):
        for item in self.children[:]:
            if isinstance(item, ui.Button) and item.custom_id in ["prev_page", "next_page"]:
                self.remove_item(item)

        prev_button = ui.Button(label="< Trước", style=discord.ButtonStyle.secondary, custom_id="prev_page", row=0, disabled=(self.current_page == 0))
        next_button = ui.Button(label="Sau >", style=discord.ButtonStyle.secondary, custom_id="next_page", row=0, disabled=(self.current_page == len(self.image_urls) - 1))
        
        prev_button.callback = self.on_page
        next_button.callback = self.on_page

        self.add_item(prev_button)
        self.add_item(next_button)

    def create_embed(self):
        # Display price prominently in the description
        description_with_price = f"**Giá bán: {self.product['price']:,}₫**\n\n{self.product['description']}"

        embed = discord.Embed(title=f"Thông tin sản phẩm: `{self.product['code']}`", description=description_with_price, color=0x6A0DAD)
        embed.set_author(name=f"Cung cấp bởi: {SELLER_INFO['name']}", icon_url=SELLER_INFO['avatar_url'])
        embed.set_image(url=self.image_urls[self.current_page])
        embed.set_footer(text=f"Hình {self.current_page + 1}/{len(self.image_urls)}")
        return embed

    async def on_page(self, interaction: discord.Interaction):
        if interaction.data["custom_id"] == "next_page":
            self.current_page += 1
        else:
            self.current_page -= 1
        
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

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
        
        view = ProductGalleryView(product)
        await interaction.followup.send(embed=view.create_embed(), view=view, ephemeral=True)

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
        await ctx.author.send("**Bắt đầu thêm sản phẩm mới...**\n\n**(1/4)** Vui lòng gửi **thông tin/mô tả** cho sản phẩm:")
        desc_msg = await bot.wait_for('message', check=check, timeout=300)
        description = desc_msg.content

        await ctx.author.send("**(2/4)** Vui lòng gửi các **ảnh** cho sản phẩm. Bạn có thể **tải ảnh lên từ máy** hoặc **dán link ảnh** vào đây. (Ảnh đầu tiên sẽ là ảnh đại diện):")
        images_msg = await bot.wait_for('message', check=check, timeout=300)
        
        image_urls_list = []
        if images_msg.attachments:
            for attachment in images_msg.attachments:
                image_urls_list.append(attachment.url)
        if images_msg.content:
            potential_urls = images_msg.content.split()
            for url in potential_urls:
                if url.startswith('http'):
                    image_urls_list.append(url)

        if not image_urls_list:
            await ctx.author.send("❌ Không có ảnh nào được cung cấp. Vui lòng thử lại với `!admin add`.")
            return
        image_urls_str = " ".join(image_urls_list)

        await ctx.author.send("**(3/4)** Vui lòng gửi **giá bán** của sản phẩm (chỉ nhập số, ví dụ: `1500000`):")
        price_msg = await bot.wait_for('message', check=check, timeout=300)
        price = int(price_msg.content)

        await ctx.author.send("**(4/4)** Vui lòng gửi **link web shop** cho sản phẩm (nếu không có, gõ `không`):")
        shop_url_msg = await bot.wait_for('message', check=check, timeout=300)
        shop_url = shop_url_msg.content if shop_url_msg.content.lower() not in ['không', 'ko', 'khong'] else None

        new_code = get_new_product_code()
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO products (code, description, image_urls, price, shop_url) VALUES (?, ?, ?, ?, ?)", (new_code, description, image_urls_str, price, shop_url))
        conn.commit()
        conn.close()

        embed = discord.Embed(title="✅ Thêm sản phẩm thành công!", color=0x00FF00)
        embed.add_field(name="Mã sản phẩm", value=new_code, inline=False)
        embed.add_field(name="Giá bán", value=f"{price:,}₫", inline=False)
        embed.add_field(name="Mô tả", value=description[:1024], inline=False)
        if shop_url:
            embed.add_field(name="Link Shop", value=shop_url, inline=False)
        embed.set_image(url=image_urls_list[0])
        await ctx.author.send(embed=embed)

    except asyncio.TimeoutError:
        await ctx.author.send("⌛ Hết thời gian. Vui lòng gõ `!admin add` để thử lại.")
    except ValueError:
        await ctx.author.send("❌ Dữ liệu không hợp lệ. Vui lòng nhập đúng định dạng. Thử lại với `!admin add`.")
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
    cursor.execute("SELECT code, price, description, image_urls, shop_url FROM products ORDER BY id")
    products = cursor.fetchall()
    conn.close()

    if not products:
        return await ctx.send("📭 Database trống, chưa có sản phẩm nào.", ephemeral=True)

    pages = []
    current_page = ""
    for p in products:
        first_image = p['image_urls'].split()[0] if p['image_urls'] else ''
        shop_link_text = f" - [Shop]({p['shop_url']})" if p['shop_url'] else ""
        line = f"**- `{p['code']}`**: {p['price']:,}₫ ([Ảnh]({first_image})){shop_link_text}\n*Mô tả: {p['description'][:70]}...*\n\n"
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
    # Reset database on start for development to apply new schema
    if os.path.exists('database.db'):
        # We only need to do this if the schema changes. Since the last change added shop_url,
        # we can comment this out for now to avoid data loss on every restart.
        # os.remove('database.db') 
        # print("Old database removed to apply new schema.")
        pass
    
    init_db() # This will create the table if it doesn't exist, safe to run.
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
