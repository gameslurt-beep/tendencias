import sys
import re
import json
import time
from urllib.parse import urlparse
from curl_cffi import requests

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

def resolve_tiktok_url_and_id(raw_url: str) -> tuple[str, str]:
    """Resolve redirecionamentos (ex: links curtos vm.tiktok.com) e extrai o ID do vídeo."""
    clean_url = raw_url.strip()
    
    # Se for link encurtado, seguir redirecionamento
    if "vm.tiktok.com" in clean_url or "/t/" in clean_url:
        try:
            r = requests.get(clean_url, impersonate="chrome124", allow_redirects=True, timeout=10)
            clean_url = r.url
        except Exception:
            pass

    # Extrair ID numérico do vídeo
    match = re.search(r'/video/(\d+)', clean_url)
    if not match:
        # Tenta pegar qualquer sequência longa de números no final
        match = re.search(r'(\d{15,25})', clean_url)

    video_id = match.group(1) if match else None
    return clean_url, video_id

def get_tiktok_metadata(canonical_url: str) -> dict:
    """Obtém metadados oficiais do vídeo via oEmbed."""
    import urllib.request
    try:
        req = urllib.request.Request(
            f"https://www.tiktok.com/oembed?url={canonical_url}",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode('utf-8'))
            title = data.get('title', 'Vídeo do TikTok').strip()
            author_nick = data.get('author_name', '')
            author_id = data.get('author_unique_id', '')
            uploader = f"@{author_id}" if author_id else f"@{author_nick}"
            if author_nick and author_id:
                uploader = f"@{author_id} ({author_nick})"
            return {
                'title': title,
                'uploader': uploader,
                'url': canonical_url,
                'platform': 'TikTok'
            }
    except Exception as e:
        # Fallback para extração rápida de metadados via yt-dlp
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'ignoreerrors': True}) as ydl:
                info = ydl.extract_info(canonical_url, download=False)
                if info:
                    return {
                        'title': (info.get('title') or 'Vídeo do TikTok').strip(),
                        'uploader': f"@{info.get('uploader') or info.get('channel') or 'criador'}",
                        'url': canonical_url,
                        'platform': 'TikTok'
                    }
        except Exception:
            pass

    return {
        'title': 'Vídeo do TikTok',
        'uploader': '@tiktok_creator',
        'url': canonical_url,
        'platform': 'TikTok'
    }



def extract_tiktok_comments(video_url: str, max_comments: int = 150) -> tuple[dict, list]:
    """Extrai comentários de qualquer vídeo do TikTok em alta velocidade usando curl_cffi."""
    print(f"\n⚡ [TikTok Engine] Conectando ao vídeo: {video_url}...")
    canonical_url, video_id = resolve_tiktok_url_and_id(video_url)

    if not video_id:
        print("❌ Não foi possível identificar o ID do vídeo na URL informada.")
        return {'title': 'Vídeo Inválido', 'uploader': 'Desconhecido', 'url': video_url, 'platform': 'TikTok'}, []

    meta = get_tiktok_metadata(canonical_url)
    print(f"🎬 Vídeo: \"{meta['title'][:60]}...\"")
    print(f"👤 Canal: {meta['uploader']}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": canonical_url,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    all_comments = []
    cursor = 0
    has_more = 1

    print(f"📥 Coletando comentários da audiência (alvo: até {max_comments})...")
    
    while len(all_comments) < max_comments and has_more:
        api_url = f"https://www.tiktok.com/api/comment/list/?aid=1988&app_language=pt-BR&app_name=tiktok_web&aweme_id={video_id}&count=20&cursor={cursor}"
        try:
            resp = requests.get(api_url, headers=headers, impersonate="chrome124", timeout=12)
            if resp.status_code != 200:
                print(f"  ⚠️ Status code da API: {resp.status_code}")
                break

            data = resp.json()
            comments_batch = data.get("comments", [])
            if not comments_batch:
                break

            for c in comments_batch:
                text = (c.get("text") or "").strip()
                if not text:
                    continue
                user = c.get("user") or {}
                unique_id = user.get("unique_id", "anonimo")
                nickname = user.get("nickname", "")
                author_display = f"@{unique_id}" + (f" ({nickname})" if nickname else "")
                
                all_comments.append({
                    "id": c.get("cid"),
                    "author": author_display,
                    "text": text,
                    "likes": c.get("digg_count", 0),
                    "timestamp": c.get("create_time")
                })

            cursor = data.get("cursor", 0)
            has_more = data.get("has_more", 0)

            print(f"  ➡️ {len(all_comments)} comentários capturados...")
            if len(all_comments) >= max_comments:
                break
            time.sleep(0.4) # Intervalo seguro

        except Exception as e:
            print(f"  ⚠️ Erro na requisição de lote: {e}")
            break

    # Deduplicação por texto
    unique_comments = []
    seen = set()
    for c in all_comments:
        if c['text'] not in seen:
            seen.add(c['text'])
            unique_comments.append(c)

    print(f"✅ [TikTok Engine] Sucesso: {len(unique_comments)} comentários únicos estruturados!")
    return meta, unique_comments

if __name__ == "__main__":
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://www.tiktok.com/@frutaverso.br/video/7690863269107600641"
    meta, comms = extract_tiktok_comments(test_url, max_comments=30)
    print("\nResultados:")
    print("Meta:", meta)
    print("Comentários extraídos:", len(comms))
    for c in comms[:5]:
        print(f"[{c['likes']} likes] {c['author']}: {c['text']}")
