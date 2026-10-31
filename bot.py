import asyncio
import os
import sys
import glob
import subprocess
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, FSInputFile
from aiogram.filters import CommandStart
import yt_dlp
from aiohttp import web

BOT_TOKEN = '9037992408:AAGXov3w-V3hdESwr1EpVEDu4H13vndJFZk'

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
user_links = {}

@dp.message(CommandStart())
async def start_cmd(message: Message):
    await message.answer("Здарова! Кидай ссылку на TikTok, Spotify или SoundCloud.")

@dp.message(F.text.startswith("http"))
async def handle_url(message: Message):
    url = message.text
    
    if "tiktok.com" not in url and "spotify.com" not in url and "soundcloud.com" not in url:
        await message.reply("Чувак, я перевариваю только ТикТок, Спотик и Саундклауд. Ютуб качай через ss!")
        return
        
    user_links[message.from_user.id] = url
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Фулл видос (или фотки)", callback_data="dl_video")],
        [InlineKeyboardButton(text="🎵 Только звук", callback_data="dl_audio")]
    ])
    await message.reply("Че качаем?", reply_markup=kb)

@dp.callback_query(F.data.in_(["dl_video", "dl_audio"]))
async def download_media(callback: CallbackQuery):
    await callback.answer()
    
    url = user_links.get(callback.from_user.id)
    if not url:
        await callback.message.answer("Бля, ссылка потерялась. Скинь еще раз.")
        return

    status_msg = await callback.message.answer("Ебашу, подожди немного...")
    is_audio = (callback.data == "dl_audio")
    
# === TIKTOK ===
    if "tiktok.com" in url:
        try:
            # Маскируемся под реального юзера с винды
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json",
            }
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.post("https://www.tikwm.com/api/", data={"url": url}) as resp:
                    # Проверяем, не кинул ли сайт нам HTML-заглушку вместо JSON
                    content_type = resp.headers.get('Content-Type', '')
                    if 'application/json' not in content_type:
                        await status_msg.edit_text("Бля, защита TikWM заблочила IP Рендера. Попробуй позже.")
                        return
                    
                    data = await resp.json()
            
            if data.get("code") == 0:
                tk_data = data["data"]
                
                if is_audio:
                    music_url = tk_data.get("music")
                    if music_url:
                        await callback.message.answer_audio(music_url)
                    else:
                        await callback.message.answer("Тут нет звука, сорян.")
                    await status_msg.delete()
                    return
                    
                if "images" in tk_data:
                    images = tk_data["images"]
                    for i in range(0, len(images), 10):
                        media_group = [InputMediaPhoto(media=img) for img in images[i:i+10]]
                        await bot.send_media_group(callback.from_user.id, media=media_group)
                    
                    if tk_data.get("music"):
                        await callback.message.answer_audio(tk_data["music"])
                        
                    await status_msg.delete()
                    return
                
                if "play" in tk_data:
                    await callback.message.answer_video(tk_data["play"])
                    await status_msg.delete()
                    return
                    
            await status_msg.edit_text("Апишка ТикТока че-то залупилась, не смог достать файл.")
        except Exception as e:
            await status_msg.edit_text(f"Пиздец с ТикТоком:\n{e}")

    # === SPOTIFY ===
    elif "spotify.com" in url:
        if not is_audio:
            await status_msg.edit_text("Ебать, это же музыка. Какой нахуй видос? Жми 'Только звук'.")
            return
            
        await status_msg.edit_text("Парсю Спотик и качаю трек, подожди немного...")
        try:
            def run_spotdl():
                # Запоминаем, какие mp3 были до скачивания
                before = set(glob.glob("*.mp3"))
                # Качаем через системный spotdl
                subprocess.run([sys.executable, "-m", "spotdl", url], check=True, capture_output=True)
                # Смотрим, какой файл появился
                after = set(glob.glob("*.mp3"))
                new_files = after - before
                return list(new_files)[0] if new_files else None

            file_name = await asyncio.to_thread(run_spotdl)
            if file_name:
                media = FSInputFile(file_name)
                await bot.send_audio(callback.from_user.id, media)
                os.remove(file_name)
                await status_msg.delete()
            else:
                await status_msg.edit_text("Бля, не смог найти скачанный трек. Спотик выебнулся.")
        except Exception as e:
            await status_msg.edit_text(f"Пиздец со Спотифаем:\n{e}")

    # === SOUNDCLOUD ===
    elif "soundcloud.com" in url:
        if not is_audio:
            await status_msg.edit_text("Бро, на Саундклауде только музыка. Жми 'Только звук'.")
            return
            
        await status_msg.edit_text("Тяну трек с Саундклауда...")
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': '%(id)s.%(ext)s',
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        try:
            def download_sc():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    return f"{info['id']}.mp3"
            
            file_name = await asyncio.to_thread(download_sc)
            media = FSInputFile(file_name)
            
            await bot.send_audio(callback.from_user.id, media)
            os.remove(file_name)
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(f"Пиздец с Саундклаудом:\n{e}")

# Заглушка для бесплатного хостинга
async def handle_ping(request):
    return web.Response(text="Бот хуярит, всё ок!")

async def main():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    
    print("Бот запущен, погнали нахуй!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
