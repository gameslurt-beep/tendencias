import sys
import os
import re
import json
import time
from playwright.sync_api import sync_playwright

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

def scrape_tiktok_profile(profile_handle_or_url: str, max_videos: int = 30) -> dict:
    """Raspa métricas e grade de vídeos de qualquer perfil do TikTok."""
    handle = profile_handle_or_url.strip()
    if not handle.startswith("http"):
        handle = handle.lstrip("@")
        profile_url = f"https://www.tiktok.com/@{handle}"
    else:
        profile_url = handle
        match = re.search(r'@([a-zA-Z0-9._-]+)', profile_url)
        handle = match.group(1) if match else "usuario"

    print(f"\n🔍 [TikTok Profile Scraper] Acessando perfil: @{handle} ({profile_url})...")

    profile_data = {
        "handle": f"@{handle}",
        "url": profile_url,
        "name": "",
        "bio": "",
        "followers": "0",
        "following": "0",
        "likes": "0",
        "videos": []
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
        )
        page = context.new_page()

        try:
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3500)

            # Rola a página para renderizar a grade
            page.mouse.wheel(0, 1000)
            page.wait_for_timeout(2000)



            # Extrair Nome e Bio
            try:
                name_el = page.locator('[data-e2e="user-subtitle"], h1').first
                if name_el.count() > 0:
                    profile_data["name"] = name_el.inner_text().strip()
            except Exception:
                pass

            try:
                bio_el = page.locator('[data-e2e="user-bio"]').first
                if bio_el.count() > 0:
                    profile_data["bio"] = bio_el.inner_text().strip().replace('\n', ' | ')
            except Exception:
                pass

            # Extrair Contadores (Seguidores, Curtidas, Seguindo)
            try:
                f_el = page.locator('[data-e2e="followers-count"]').first
                if f_el.count() > 0:
                    profile_data["followers"] = f_el.inner_text().strip()
            except Exception:
                pass

            try:
                l_el = page.locator('[data-e2e="likes-count"]').first
                if l_el.count() > 0:
                    profile_data["likes"] = l_el.inner_text().strip()
            except Exception:
                pass

            try:
                fg_el = page.locator('[data-e2e="following-count"]').first
                if fg_el.count() > 0:
                    profile_data["following"] = fg_el.inner_text().strip()
            except Exception:
                pass

            # Aguarda a grade assentar
            page.wait_for_timeout(1500)


            # Capturar links e descrições dos vídeos
            links = page.locator('a').all()
            print(f"DEBUG: Total tags <a> encontradas: {len(links)}")
            seen_ids = set()
            for l in links:
                href = l.get_attribute("href") or ""
                if "/video/" not in href:
                    continue


                if href.startswith("/"):
                    href = f"https://www.tiktok.com{href}"

                v_id = href.split("/video/")[-1].split("?")[0]
                if not v_id or v_id in seen_ids:
                    continue
                seen_ids.add(v_id)

                raw_text = l.inner_text().replace('\n', ' ').strip()
                profile_data["videos"].append({
                    "id": v_id,
                    "url": href,
                    "preview_text": raw_text
                })

                if len(profile_data["videos"]) >= max_videos:
                    break


        except Exception as e:
            print(f"⚠️ Aviso na raspagem do perfil: {e}")
        finally:
            browser.close()

    print(f"✅ [@{handle}] Seguidores: {profile_data['followers']} | Curtidas: {profile_data['likes']} | Vídeos extraídos: {len(profile_data['videos'])}")
    return profile_data

def generate_profile_report(profile_data: dict, output_dir: str = "output/perfis") -> str:
    """Salva um relatório estruturado do perfil em Markdown e JSON."""
    os.makedirs(output_dir, exist_ok=True)
    slug = profile_data['handle'].lstrip('@')
    report_file = os.path.join(output_dir, f"perfil_{slug}.md")
    json_file = os.path.join(output_dir, f"perfil_{slug}.json")

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(profile_data, f, ensure_ascii=False, indent=2)

    with open(report_file, "w", encoding="utf-8") as f:
        f.write(f"# 👤 Raio-X de Perfil do TikTok: {profile_data['handle']}\n\n")
        f.write(f"- 🔗 **Perfil:** [{profile_data['url']}]({profile_data['url']})\n")
        f.write(f"- 🏷️ **Nome:** {profile_data['name']}\n")
        f.write(f"- 👥 **Seguidores:** {profile_data['followers']}\n")
        f.write(f"- ❤️ **Total de Curtidas:** {profile_data['likes']}\n")
        f.write(f"- 📝 **Biografia:** {profile_data['bio']}\n")
        f.write(f"- 🎬 **Vídeos Raspados:** {len(profile_data['videos'])}\n")
        f.write(f"- 📅 **Data da Raspagem:** {time.strftime('%d/%m/%Y %H:%M:%S')}\n\n")
        f.write("---\n\n")

        f.write("## 🎬 Grade de Vídeos Identificados\n\n")
        for idx, v in enumerate(profile_data['videos'], 1):
            f.write(f"### {idx}. Vídeo {v['id']}\n")
            f.write(f"- 🔗 **Link:** [{v['url']}]({v['url']})\n")
            if v['preview_text']:
                f.write(f"- 📊 **Estatística/Legenda:** `{v['preview_text']}`\n")
            f.write("\n")

    print(f"📁 Relatório salvo em: {os.path.abspath(report_file)}")
    return report_file

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "@wesleyalexandreofc"
    data = scrape_tiktok_profile(target, max_videos=20)
    generate_profile_report(data)
