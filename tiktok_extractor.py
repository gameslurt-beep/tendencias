import re
import json
import time
from playwright.sync_api import sync_playwright

def extract_tiktok_comments(video_url: str, max_comments: int = 50, headless: bool = True):
    print(f"\n🔍 [TikTok Engine] Abrindo navegador para extrair comentários de: {video_url}...")
    
    captured_comments = []
    video_title = "TikTok Video"
    author_name = "TikTok Creator"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        # Interceptar chamadas da API interna de comentários
        def handle_response(response):
            nonlocal captured_comments
            if "comment/list" in response.url:
                try:
                    data = response.json()
                    comments = data.get("comments", [])
                    for c in comments:
                        text = c.get("text", "").strip()
                        if not text:
                            continue
                        user = c.get("user", {})
                        captured_comments.append({
                            "id": c.get("cid"),
                            "author": f"@{user.get('unique_id', 'anonimo')} ({user.get('nickname', '')})",
                            "text": text,
                            "likes": c.get("digg_count", 0),
                            "timestamp": c.get("create_time")
                        })
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            page.goto(video_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(3)

            # Tenta pegar título e autor da página
            try:
                title_elem = page.locator('h1, [data-e2e="browse-video-desc"]').first
                if title_elem.count() > 0:
                    video_title = title_elem.inner_text().strip().replace('\n', ' ')[:80]
            except Exception:
                pass

            try:
                author_elem = page.locator('[data-e2e="browser-nickname"], [data-e2e="user-title"]').first
                if author_elem.count() > 0:
                    author_name = author_elem.inner_text().strip()
            except Exception:
                pass

            # Rolar suavemente para baixo para carregar os comentários
            for _ in range(5):
                page.mouse.wheel(0, 800)
                time.sleep(1.5)
                if len(captured_comments) >= max_comments:
                    break

            # Se a interceptação pegou menos que o esperado, tentar ler o DOM direto
            if not captured_comments:
                print("  🛡️ Lendo nós visuais do DOM dos comentários...")
                comment_nodes = page.locator('[data-e2e="comment-level-1"]').all()
                for node in comment_nodes[:max_comments]:
                    try:
                        text = node.locator('p, span').first.inner_text().strip()
                        if text:
                            captured_comments.append({
                                "id": str(time.time()),
                                "author": "@usuario",
                                "text": text,
                                "likes": 0,
                                "timestamp": int(time.time())
                            })
                    except Exception:
                        pass

        except Exception as e:
            print(f"  ⚠️ Aviso no carregamento: {e}")
        finally:
            browser.close()

    # Deduplicar por texto
    unique_comments = []
    seen = set()
    for c in captured_comments:
        if c['text'] not in seen:
            seen.add(c['text'])
            unique_comments.append(c)

    print(f"✅ [TikTok Engine] {len(unique_comments)} comentários capturados com sucesso!")
    return {
        'title': video_title,
        'uploader': author_name,
        'url': video_url,
        'platform': 'TikTok'
    }, unique_comments

if __name__ == "__main__":
    import sys
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://www.tiktok.com"
    meta, comms = extract_tiktok_comments(test_url, max_comments=10)
    print("Meta:", meta)
    print("Comentários extraídos:", len(comms))
