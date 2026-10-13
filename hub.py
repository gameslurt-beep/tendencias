import os
import sys
import json
import re
import time
import argparse
import urllib.request
import urllib.parse
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configura encoding UTF-8 no terminal Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import yt_dlp
import httpx
from bs4 import BeautifulSoup
import warnings
warnings.filterwarnings("ignore")

# Fallback opcional para Whisper local se necessário
try:
    from faster_whisper import WhisperModel
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False

YTDL_BASE_OPTS = {
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web']
        }
    },
    'quiet': True,
    'no_warnings': True,
    'ignoreerrors': True,
}

# ==============================================================================
# 1. FUNÇÕES AUXILIARES E TRANSCRIÇÃO (YOUTUBE TURBO)
# ==============================================================================

def clean_target_url(url_or_handle: str) -> str:
    url = url_or_handle.strip()
    if not url.startswith("http"):
        if url.startswith("@"):
            url = f"https://www.youtube.com/{url}"
        elif len(url) == 11 and not "/" in url:
            return f"https://www.youtube.com/watch?v={url}"
        else:
            url = f"https://www.youtube.com/@{url}"

    if "/shorts/" in url:
        short_id = url.split("/shorts/")[-1].split("?")[0].split("/")[0]
        return f"https://www.youtube.com/watch?v={short_id}"
    elif "youtu.be/" in url:
        video_id = url.split("youtu.be/")[-1].split("?")[0].split("/")[0]
        return f"https://www.youtube.com/watch?v={video_id}"

    if ("/channel/" in url or "/@" in url or "/c/" in url) and not any(sub in url for sub in ["/videos", "/shorts", "/streams", "/playlists", "watch?v="]):
        url = url.rstrip("/") + "/videos"
    return url

def parse_json3_data(data: dict):
    events = data.get('events', [])
    full_text = []
    hook_text = []
    snippets = []

    for ev in events:
        t_start = ev.get('tStartMs', 0) / 1000.0
        t_dur = ev.get('dDurationMs', 0) / 1000.0
        segs = ev.get('segs', [])
        seg_text = "".join(s.get('utf8', '') for s in segs).strip()
        clean_t = seg_text.replace('\n', ' ').strip()
        if not clean_t or clean_t == "[Música]":
            continue

        full_text.append(clean_t)
        snippets.append({'start': t_start, 'duration': t_dur, 'text': clean_t})
        if t_start <= 35.0:
            hook_text.append(clean_t)

    return {
        'full_text': " ".join(full_text),
        'hook_text': " ".join(hook_text),
        'snippets': snippets,
    }

def fetch_caption_direct(caption_url: str):
    try:
        req = urllib.request.Request(
            caption_url,
            headers={'User-Agent': 'com.google.android.youtube/19.29.37 (Linux; U; Android 11)'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            raw = response.read().decode('utf-8')
            return parse_json3_data(json.loads(raw))
    except Exception:
        return None

def extract_captions_from_info(info: dict):
    captions_dict = {}
    if 'subtitles' in info and info['subtitles']:
        captions_dict.update(info['subtitles'])
    if 'automatic_captions' in info and info['automatic_captions']:
        for k, v in info['automatic_captions'].items():
            if k not in captions_dict:
                captions_dict[k] = v

    if not captions_dict:
        return None

    preferred_langs = ['pt-orig', 'pt', 'pt-BR', 'en', 'en-US']
    selected_track = None
    lang_found = None

    for pl in preferred_langs:
        if pl in captions_dict:
            for tr in captions_dict[pl]:
                if tr.get('ext') == 'json3':
                    selected_track = tr
                    lang_found = pl
                    break
            if selected_track:
                break
            if captions_dict[pl]:
                selected_track = captions_dict[pl][0]
                lang_found = pl
                break

    if not selected_track:
        for lang, tracks in captions_dict.items():
            for tr in tracks:
                if tr.get('ext') == 'json3':
                    selected_track = tr
                    lang_found = lang
                    break
            if selected_track:
                break

    if selected_track and 'url' in selected_track:
        res = fetch_caption_direct(selected_track['url'])
        if res and res.get('full_text'):
            res['source'] = f"Legendas ({lang_found})"
            return res

    return None

def process_single_video(video_url: str, use_whisper: bool = False):
    ydl_opts = {
        **YTDL_BASE_OPTS,
        'extract_flat': False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if not info:
                return None

            video_id = info.get('id')
            title = info.get('title', 'Sem título')
            duration = info.get('duration')
            view_count = info.get('view_count')
            uploader = info.get('uploader') or info.get('channel') or "Canal"

            transcript = extract_captions_from_info(info)

            return {
                'id': video_id,
                'title': title,
                'url': f"https://www.youtube.com/watch?v={video_id}",
                'duration': duration,
                'view_count': view_count,
                'uploader': uploader,
                'transcript': transcript
            }
    except Exception:
        return None

def format_duration(seconds):
    if not seconds:
        return "N/A"
    return str(timedelta(seconds=int(seconds)))

def save_analysis(folder_name: str, results: list, output_dir: str = "output"):
    os.makedirs(output_dir, exist_ok=True)
    slug = re.sub(r'[^a-zA-Z0-9_-]', '_', folder_name).strip('_') or "resultado"
    channel_folder = os.path.join(output_dir, slug)
    os.makedirs(channel_folder, exist_ok=True)

    json_path = os.path.join(channel_folder, "dados_completos.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    report_path = os.path.join(channel_folder, "relatorio_ganchos_e_videos.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# 📊 Análise de Engenharia Reversa e Ganchos: {folder_name}\n\n")
        f.write(f"Total de itens analisados: **{len(results)}**\n\n")
        f.write("---\n\n")

        for idx, item in enumerate(results, 1):
            f.write(f"### {idx}. {item['title']}\n")
            f.write(f"- 🔗 **URL:** [{item['url']}]({item['url']})\n")
            f.write(f"- 👤 **Canal:** {item.get('uploader', 'N/A')}\n")
            f.write(f"- ⏱️ **Duração:** {format_duration(item.get('duration'))}\n")
            views = f"{item['view_count']:,}" if item.get('view_count') else "N/A"
            f.write(f"- 👁️ **Visualizações:** {views}\n")

            transcript_data = item.get('transcript')
            if transcript_data and 'hook_text' in transcript_data and transcript_data['hook_text']:
                f.write(f"- 🎙️ **Fonte:** {transcript_data.get('source')}\n")
                f.write(f"\n> **🎣 Gancho Inicial (Primeiros 30s):**\n")
                f.write(f"> *\"{transcript_data['hook_text']}\"*\n\n")
                words_count = len(transcript_data['full_text'].split())
                f.write(f"- 📝 **Total de palavras:** {words_count}\n")
            else:
                f.write("\n⚠️ *Transcrição indisponível.*\n\n")
            f.write("\n---\n\n")

    transcripts_folder = os.path.join(channel_folder, "transcricoes")
    os.makedirs(transcripts_folder, exist_ok=True)

    transcribed_count = 0
    for item in results:
        t_data = item.get('transcript')
        if t_data and t_data.get('full_text'):
            transcribed_count += 1
            safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', item['title'])[:50]
            txt_file = os.path.join(transcripts_folder, f"{item['id']}_{safe_title}.txt")
            with open(txt_file, "w", encoding="utf-8") as tf:
                tf.write(f"Título: {item['title']}\n")
                tf.write(f"Canal: {item.get('uploader')}\n")
                tf.write(f"URL: {item['url']}\n")
                tf.write("=" * 60 + "\n")
                tf.write("🎣 GANCHO INICIAL (PRIMEIROS 30S):\n")
                tf.write(t_data.get('hook_text', '') + "\n")
                tf.write("=" * 60 + "\n\n")
                tf.write("📜 TRANSCRIÇÃO COMPLETA:\n")
                tf.write(t_data['full_text'])

    print(f"\n=======================================================")
    print(f"🎉 Processamento Concluído!")
    print(f"📊 Vídeos processados: {len(results)} | Transcritos: {transcribed_count}")
    print(f"📁 Relatório Markdown: {os.path.abspath(report_path)}")
    print(f"📁 Transcrições: {os.path.abspath(transcripts_folder)}")
    print(f"📁 Dados JSON: {os.path.abspath(json_path)}")
    print(f"=======================================================\n")

# ==============================================================================
# 2. MÓDULO 1: EXTRAIR & TRANSCREVER CANAL OU VÍDEO
# ==============================================================================

def execute_youtube_channel_transcription(target_url=None, max_videos=10, popular=False):
    if not target_url:
        target_url = input("\n👉 Digite o link do canal, @handle ou vídeo: ").strip()
        if not target_url:
            return
        num_in = input("👉 Quantos vídeos analisar? [Padrão: 10]: ").strip()
        max_videos = int(num_in) if num_in.isdigit() else 10
        pop_in = input("👉 Ordenar pelos mais populares? (s/n) [Padrão: n]: ").strip().lower()
        popular = pop_in.startswith('s')

    clean_url = clean_target_url(target_url)
    print(f"\n🔍 Buscando vídeos em: {clean_url}...")

    video_items = []
    if "watch?v=" in clean_url:
        video_items = [{'url': clean_url, 'id': clean_url.split('v=')[-1].split('&')[0]}]
    else:
        target_list_url = clean_url
        if popular and "/videos" in target_list_url:
            target_list_url += "?view=0&sort=p&flow=grid"

        ydl_opts = {
            **YTDL_BASE_OPTS,
            'extract_flat': 'in_playlist',
            'playlistend': max_videos,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            res = ydl.extract_info(target_list_url, download=False)
            if res:
                entries = res.get('entries', [res])
                for e in entries:
                    if e and e.get('id'):
                        video_items.append({'id': e['id'], 'url': f"https://www.youtube.com/watch?v={e['id']}"})

    if not video_items:
        print("❌ Nenhum vídeo encontrado.")
        return

    print(f"⚡ Extraindo {len(video_items)} vídeo(s) com 5 threads paralelas...")
    results = []
    with ThreadPoolExecutor(max_workers=min(5, len(video_items))) as executor:
        futures = {executor.submit(process_single_video, item['url']): item for item in video_items}
        for future in as_completed(futures):
            res = future.result()
            if res:
                results.append(res)
                hook = res.get('transcript', {}).get('hook_text', '') if res.get('transcript') else ''
                status = f"🎣 Gancho: \"{hook[:45]}...\"" if hook else "⚠️ Sem legenda"
                print(f"  ✔️ [{len(results)}/{len(video_items)}] {res['title'][:40]} -> {status}")

    if results:
        save_analysis(results[0].get('uploader') or "Canal_Extraido", results)

# ==============================================================================
# 3. MÓDULO 2: PESQUISAR VÍDEOS & CANAIS EM ALTA POR NICHO/TEMA (YOUTUBE)
# ==============================================================================

def execute_youtube_niche_search(query=None, limit=10):
    if not query:
        query = input("\n👉 Digite o nicho ou termo de pesquisa (ex.: inteligência artificial, cripto): ").strip()
        if not query:
            return
        num_in = input("👉 Quantos vídeos analisar? [Padrão: 10]: ").strip()
        limit = int(num_in) if num_in.isdigit() else 10

    print(f"\n🔍 Buscando os vídeos mais relevantes sobre '{query}' no YouTube...")
    search_query = f"ytsearch{limit}:{query}"
    
    ydl_opts = {
        **YTDL_BASE_OPTS,
        'extract_flat': 'in_playlist',
    }

    videos_found = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        res = ydl.extract_info(search_query, download=False)
        if res and 'entries' in res:
            for e in res['entries']:
                if not e:
                    continue
                videos_found.append({
                    'id': e.get('id'),
                    'title': e.get('title'),
                    'url': f"https://www.youtube.com/watch?v={e.get('id')}",
                    'uploader': e.get('uploader') or e.get('channel') or "Desconhecido",
                    'channel_url': e.get('channel_url') or e.get('uploader_url'),
                    'view_count': e.get('view_count') or 0,
                    'duration': e.get('duration'),
                })

    if not videos_found:
        print("❌ Nenhum vídeo encontrado para essa busca.")
        return

    # Ordenar por visualizações decrescentes
    videos_found.sort(key=lambda x: x['view_count'], reverse=True)

    print("\n" + "=" * 65)
    print(f" 🏆 TOP VÍDEOS E CANAIS NO NICHO: '{query}'")
    print("=" * 65)

    channel_stats = {}
    for idx, v in enumerate(videos_found, 1):
        views_formatted = f"{v['view_count']:,}" if v['view_count'] else "N/A"
        dur_str = format_duration(v['duration'])
        print(f"{idx}. [{views_formatted} views] {v['title'][:55]}")
        print(f"   👤 Canal: {v['uploader']} | ⏱️ {dur_str} | 🔗 {v['url']}")
        
        # Agregar estatísticas por canal
        u = v['uploader']
        if u not in channel_stats:
            channel_stats[u] = {'count': 0, 'views': 0, 'url': v.get('channel_url')}
        channel_stats[u]['count'] += 1
        channel_stats[u]['views'] += v['view_count']

    # Exibir canais dominantes
    print("\n👑 CANAIS DOMINANTES NESSE TEMA:")
    sorted_channels = sorted(channel_stats.items(), key=lambda x: x[1]['views'], reverse=True)
    for ch, data in sorted_channels[:5]:
        print(f"   • {ch}: {data['views']:,} visualizações no total analisado ({data['count']} vídeo(s))")

    # Perguntar se deseja transcrever e extrair ganchos
    transcribe_opt = input("\n👉 Deseja transcrever e extrair os GANCHOS desses vídeos agora? (s/n) [Padrão: s]: ").strip().lower()
    if transcribe_opt != 'n':
        print(f"\n⚡ Extraindo transcrições e ganchos dos {len(videos_found)} vídeos em paralelo...")
        results = []
        with ThreadPoolExecutor(max_workers=min(5, len(videos_found))) as executor:
            futures = {executor.submit(process_single_video, item['url']): item for item in videos_found}
            for future in as_completed(futures):
                res = future.result()
                if res:
                    results.append(res)
                    hook = res.get('transcript', {}).get('hook_text', '') if res.get('transcript') else ''
                    status = f"🎣 Gancho: \"{hook[:40]}...\"" if hook else "⚠️ Sem legenda"
                    print(f"  ✔️ [{len(results)}/{len(videos_found)}] {res['title'][:35]} -> {status}")

        if results:
            save_analysis(f"Nicho_{query}", results)

# ==============================================================================
# 4. MÓDULO 3: RADAR DE TENDÊNCIAS DO REDDIT (DORES E TÓPICOS QUENTES)
# ==============================================================================

def execute_reddit_trends(subreddit=None, limit=10):
    if not subreddit:
        subreddit = input("\n👉 Digite o Subreddit ou Tema (ex.: investimentos, tecnologia, brasil, crypto): ").strip()
        if not subreddit:
            return
        num_in = input("👉 Quantos tópicos coletar? [Padrão: 10]: ").strip()
        limit = int(num_in) if num_in.isdigit() else 10

    clean_input = subreddit.replace('@', '').strip()
    is_specific_sub = " " not in clean_input and not clean_input.startswith("http")
    sub_name = clean_input.replace('r/', '') if is_specific_sub else "reddit"

    print(f"\n🔍 Buscando discussões e relatos no Reddit sobre: '{clean_input}'...")

    posts = []
    # Estratégia 1: Se for subreddit único, tenta RSS
    if is_specific_sub:
        rss_url = f"https://www.reddit.com/r/{sub_name}.rss"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0'}
        try:
            r = httpx.get(rss_url, headers=headers, timeout=6.0, follow_redirects=True)
            if r.status_code == 200 and len(r.text) > 500:
                soup = BeautifulSoup(r.text, 'html.parser')
                entries = soup.find_all('entry')
                for e in entries[:limit]:
                    title = e.find('title').text if e.find('title') else 'Sem título'
                    link_tag = e.find('link')
                    link = link_tag.get('href') if link_tag else ''
                    content_tag = e.find('content')
                    body_clean = ""
                    if content_tag:
                        c_soup = BeautifulSoup(content_tag.text, 'html.parser')
                        body_clean = c_soup.get_text().strip().replace('\n', ' ')[:250]
                    posts.append({'title': title, 'link': link, 'content': body_clean})
        except Exception:
            pass

    # Estratégia 2: Busca indexada DuckDuckGo (funciona para dúvidas livres e para subreddits)
    if not posts:
        print("    🛡️ Consultando tópicos indexados e comunidades especializadas...")
        try:
            ddg_url = "https://html.duckduckgo.com/html/"
            if is_specific_sub:
                ddg_query = f"site:reddit.com/r/{sub_name}"
            else:
                ddg_query = f"site:reddit.com {clean_input}"

            r_ddg = httpx.post(ddg_url, data={'q': ddg_query}, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}, timeout=8.0)
            if r_ddg.status_code == 200:
                soup = BeautifulSoup(r_ddg.text, 'html.parser')
                results = soup.find_all('div', class_='result')
                for res in results[:limit]:
                    title_elem = res.find('a', class_='result__snippet')
                    link_elem = res.find('a', class_='result__url')
                    header_elem = res.find('a', class_='result__a')
                    title = header_elem.text.strip() if header_elem else 'Post Reddit'
                    link = link_elem.get('href', '').strip() if link_elem else ''
                    snippet = title_elem.text.strip() if title_elem else ''
                    if "reddit.com" in link or snippet:
                        posts.append({'title': title, 'link': link, 'content': snippet})
        except Exception as e:
            print(f"    ⚠️ Erro na consulta: {e}")

    if not posts:
        print("❌ Não foi possível carregar tópicos do Reddit no momento.")
        return

    print("\n" + "=" * 65)
    print(f" 🔥 PRINCIPAIS TÓPICOS & DISCUSSÕES EM: r/{clean_sub}")
    print("=" * 65)

    os.makedirs("output/reddit", exist_ok=True)
    report_file = os.path.join("output/reddit", f"tendencias_{clean_sub}.md")

    with open(report_file, "w", encoding="utf-8") as f:
        f.write(f"# 👽 Tendências e Dores do Público: r/{clean_sub}\n\n")
        f.write(f"Coletado em: {time.strftime('%d/%m/%Y %H:%M:%S')}\n\n")
        f.write("---\n\n")

        for idx, p in enumerate(posts, 1):
            print(f"\n{idx}. 📌 {p['title']}")
            if p['content']:
                print(f"   💬 Trecho: \"{p['content'][:120]}...\"")
            print(f"   🔗 {p['link']}")

            f.write(f"### {idx}. {p['title']}\n")
            f.write(f"- 🔗 **Link:** [{p['link']}]({p['link']})\n")
            if p['content']:
                f.write(f"- 💬 **Resumo/Discussão:** {p['content']}\n")
            f.write("\n---\n\n")

    print(f"\n📁 Relatório do Reddit salvo em: {os.path.abspath(report_file)}")

# ==============================================================================
# 5. MÓDULO 4: MÁQUINA COMPLETA DE CONTEÚDO (REDDIT -> YOUTUBE)
# ==============================================================================

def execute_cross_content_machine():
    niche = input("\n👉 Qual é o seu nicho ou tema? (ex.: investimentos, produtividade, inteligência artificial): ").strip()
    if not niche:
        return

    print(f"\n[Etapa 1/2] 👽 Mapeando o que as pessoas estão discutindo no Reddit sobre '{niche}'...")
    execute_reddit_trends(subreddit=niche, limit=5)

    print(f"\n[Etapa 2/2] 🎥 Cruzando com os vídeos mais assistidos no YouTube sobre '{niche}'...")
    execute_youtube_niche_search(query=niche, limit=5)

# ==============================================================================
# MENU PRINCIPAL INTERATIVO
# ==============================================================================

def menu():
    while True:
        print("\n" + "=" * 65)
        print("  🎯 VIRAL RADAR & REVERSE ENGINEERING HUB (ALL-IN-ONE)")
        print("=" * 65)
        print("1. 🎬 Analisar Canal ou Vídeo do YouTube (Transcrição + Ganchos)")
        print("2. 🔍 Buscar Vídeos & Canais em Alta no YouTube por Nicho/Tema")
        print("3. 👽 Radar de Tendências do Reddit (Dores e Tópicos Quentes)")
        print("4. ⚡ Máquina Completa de Conteúdo (Reddit ➔ YouTube ➔ Ganchos)")
        print("0. ❌ Sair")
        print("=" * 65)

        choice = input("👉 Escolha uma opção [0-4]: ").strip()

        if choice == "1":
            execute_youtube_channel_transcription()
        elif choice == "2":
            execute_youtube_niche_search()
        elif choice == "3":
            execute_reddit_trends()
        elif choice == "4":
            execute_cross_content_machine()
        elif choice == "0":
            print("\n👋 Encerrando. Até logo!")
            break
        else:
            print("Opção inválida. Tente novamente.")

if __name__ == "__main__":
    menu()
