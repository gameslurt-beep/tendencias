import os
import sys
import json
import re
import argparse
import urllib.request
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# Forçar stdout e stderr em UTF-8 no Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import yt_dlp

# Tenta carregar faster-whisper para fallback local opcional
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

def clean_target_url(url_or_handle: str) -> str:
    """Padroniza URL, handle ou link de vídeo/canal."""
    url = url_or_handle.strip()
    if not url.startswith("http"):
        if url.startswith("@"):
            url = f"https://www.youtube.com/{url}"
        elif len(url) == 11 and not "/" in url:
            return f"https://www.youtube.com/watch?v={url}"
        else:
            url = f"https://www.youtube.com/@{url}"
    
    # Suporte a links /shorts/ e youtu.be/
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
    """Extrai texto e gancho de um payload json3 já carregado na memória."""
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
    """Baixa o json3 diretamente pela URL assinada em milissegundos na memória."""
    try:
        req = urllib.request.Request(
            caption_url,
            headers={'User-Agent': 'com.google.android.youtube/19.29.37 (Linux; U; Android 11)'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            raw = response.read().decode('utf-8')
            data = json.loads(raw)
            return parse_json3_data(data)
    except Exception:
        return None

def extract_captions_from_info(info: dict):
    """Localiza a melhor legenda (pt-orig, pt, en, etc.) direto dos metadados e baixa em memória."""
    captions_dict = {}
    
    # 1. Legendas manuais (prioridade máxima se existirem)
    if 'subtitles' in info and info['subtitles']:
        captions_dict.update(info['subtitles'])
    
    # 2. Legendas automáticas
    if 'automatic_captions' in info and info['automatic_captions']:
        for k, v in info['automatic_captions'].items():
            if k not in captions_dict:
                captions_dict[k] = v

    if not captions_dict:
        return None

    # Ordem de preferência de idiomas
    preferred_langs = ['pt-orig', 'pt', 'pt-BR', 'en', 'en-US']
    selected_track = None
    lang_found = None

    for pl in preferred_langs:
        if pl in captions_dict:
            tracks = captions_dict[pl]
            # Prioriza formato json3
            for tr in tracks:
                if tr.get('ext') == 'json3':
                    selected_track = tr
                    lang_found = pl
                    break
            if selected_track:
                break
            if tracks:
                selected_track = tracks[0]
                lang_found = pl
                break

    # Se não achou na lista preferida, pega a primeira disponível em json3
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
            res['source'] = f"YouTube Captions Direct ({lang_found})"
            return res

    return None

def process_single_video(video_url: str, use_whisper: bool = False, video_hint: dict = None):
    """
    Processa um único vídeo em alta velocidade:
    Extrai metadados + legenda assinada em uma única chamada de rede.
    """
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

            # Transcrição direta em memória (ultra-rápida)
            transcript = extract_captions_from_info(info)

            # Fallback opcional com Whisper se não houver legenda
            if not transcript and use_whisper and HAS_WHISPER:
                print(f"    [Fallback] Transcrevendo {title[:40]} com Whisper local...")
                transcript = transcribe_with_whisper(video_id)

            return {
                'id': video_id,
                'title': title,
                'url': f"https://www.youtube.com/watch?v={video_id}",
                'duration': duration,
                'view_count': view_count,
                'uploader': uploader,
                'transcript': transcript
            }
    except Exception as e:
        return None

def transcribe_with_whisper(video_id: str, model_size: str = "base"):
    """Fallback local para quando o vídeo não possuir nenhuma legenda."""
    audio_path = f"temp_{video_id}.mp3"
    ydl_opts = {
        **YTDL_BASE_OPTS,
        'format': 'bestaudio/best',
        'outtmpl': f"temp_{video_id}.%(ext)s",
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

        if not os.path.exists(audio_path):
            return None

        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio_path, beam_size=5)

        full_text = []
        hook_text = []
        snippets = []

        for segment in segments:
            clean_t = segment.text.strip()
            full_text.append(clean_t)
            snippets.append({'start': segment.start, 'duration': segment.end - segment.start, 'text': clean_t})
            if segment.start <= 35.0:
                hook_text.append(clean_t)

        if os.path.exists(audio_path):
            os.remove(audio_path)

        return {
            'full_text': " ".join(full_text),
            'hook_text': " ".join(hook_text),
            'snippets': snippets,
            'source': f"Faster-Whisper ({info.language})",
        }
    except Exception:
        if os.path.exists(audio_path):
            os.remove(audio_path)
        return None

def get_channel_video_list(target_url: str, max_videos: int = 10, sort_popular: bool = False):
    """Obtém rapidamente a lista de IDs do canal em uma única chamada plana."""
    url = clean_target_url(target_url)
    if "watch?v=" in url:
        return [{'url': url, 'id': url.split('v=')[-1].split('&')[0]}]

    if sort_popular and "/videos" in url:
        url = url + "?view=0&sort=p&flow=grid"

    ydl_opts = {
        **YTDL_BASE_OPTS,
        'extract_flat': 'in_playlist',
        'playlistend': max_videos,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        res = ydl.extract_info(url, download=False)
        if not res:
            return []
        entries = res.get('entries', [res])
        urls = []
        for e in entries:
            if e and e.get('id'):
                urls.append({
                    'id': e['id'],
                    'url': f"https://www.youtube.com/watch?v={e['id']}",
                    'title': e.get('title')
                })
        return urls

def format_duration(seconds):
    if not seconds:
        return "N/A"
    return str(timedelta(seconds=int(seconds)))

def save_analysis(channel_name: str, results: list, output_dir: str = "output"):
    """Salva relatórios consolidados em Markdown, JSON e arquivos de texto."""
    os.makedirs(output_dir, exist_ok=True)
    slug = re.sub(r'[^a-zA-Z0-9_-]', '_', channel_name).strip('_')
    if not slug:
        slug = "canal"

    channel_folder = os.path.join(output_dir, slug)
    os.makedirs(channel_folder, exist_ok=True)

    json_path = os.path.join(channel_folder, "dados_completos.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    report_path = os.path.join(channel_folder, "relatorio_ganchos_e_videos.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# 📊 Análise de Engenharia Reversa e Ganchos: {channel_name}\n\n")
        f.write(f"Total de vídeos extraídos: **{len(results)}**\n\n")
        f.write("Este relatório destaca a abertura (**Gancho / Primeiros 30s**) e transcrição dos conteúdos analisados.\n\n")
        f.write("---\n\n")

        for idx, item in enumerate(results, 1):
            f.write(f"### {idx}. {item['title']}\n")
            f.write(f"- 🔗 **URL:** [{item['url']}]({item['url']})\n")
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
                tf.write(f"Canal: {channel_name}\n")
                tf.write(f"URL: {item['url']}\n")
                tf.write(f"Fonte: {t_data.get('source')}\n\n")
                tf.write("=" * 60 + "\n")
                tf.write("🎣 GANCHO INICIAL (PRIMEIROS 30S):\n")
                tf.write(t_data.get('hook_text', '') + "\n")
                tf.write("=" * 60 + "\n\n")
                tf.write("📜 TRANSCRIÇÃO COMPLETA:\n")
                tf.write(t_data['full_text'])

    print(f"\n=======================================================")
    print(f"⚡ Extração Ultra-Rápida Concluída!")
    print(f"📊 Vídeos processados: {len(results)} | Transcritos: {transcribed_count}")
    print(f"📁 Arquivos salvos em:")
    print(f"   👉 Relatório: {os.path.abspath(report_path)}")
    print(f"   👉 Transcrições: {os.path.abspath(transcripts_folder)}")
    print(f"   👉 JSON: {os.path.abspath(json_path)}")
    print(f"=======================================================\n")

def main():
    parser = argparse.ArgumentParser(description="Extrator Ultra-Rápido de Vídeos e Transcrições")
    parser.add_argument("target", nargs="?", help="URL do canal, @handle ou link de vídeo")
    parser.add_argument("-n", "--num", type=int, default=10, help="Quantidade de vídeos para coletar (padrão: 10)")
    parser.add_argument("--popular", action="store_true", help="Buscar vídeos mais populares do canal")
    parser.add_argument("--whisper", action="store_true", help="Usar Faster-Whisper local como fallback se não houver legenda")
    parser.add_argument("-w", "--workers", type=int, default=5, help="Número de threads simultâneas (padrão: 5)")
    
    args = parser.parse_args()

    channel_input = args.target
    if not channel_input:
        print("\n" + "=" * 55)
        print("  ⚡ YOUTUBE EXTRACTOR & TRANSCRIBER (TURBO)")
        print("=" * 55)
        channel_input = input("\n👉 Digite o link do canal, @handle ou vídeo: ").strip()
        if not channel_input:
            print("Entrada vazia. Encerrando.")
            return

        num_in = input("👉 Quantos vídeos analisar? [Padrão: 10]: ").strip()
        max_v = int(num_in) if num_in.isdigit() else 10

        pop_in = input("👉 Ordenar pelos Mais Populares? (s/n) [Padrão: n]: ").strip().lower()
        sort_popular = pop_in.startswith('s')
        
        whisper_in = input("👉 Ativar Whisper local se não houver legenda? (s/n) [Padrão: n]: ").strip().lower()
        use_whisper = whisper_in.startswith('s')
        workers = 5
    else:
        max_v = args.num
        sort_popular = args.popular
        use_whisper = args.whisper
        workers = args.workers

    print(f"\n🚀 Iniciando extração acelerada (Threads paralelas: {workers})...")
    
    video_items = get_channel_video_list(channel_input, max_videos=max_v, sort_popular=sort_popular)
    if not video_items:
        print("❌ Nenhum vídeo encontrado.")
        return

    print(f"✅ {len(video_items)} vídeo(s) na fila de processamento paralelo.")

    results = []
    # Processamento paralelo com ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(workers, len(video_items))) as executor:
        future_to_item = {
            executor.submit(process_single_video, item['url'], use_whisper, item): item 
            for item in video_items
        }
        for future in as_completed(future_to_item):
            item = future_to_item[future]
            res = future.result()
            if res:
                results.append(res)
                hook = res.get('transcript', {}).get('hook_text', '') if res.get('transcript') else ''
                status = f"🎣 Gancho: \"{hook[:50]}...\"" if hook else "⚠️ Sem transcrição direta"
                print(f"  ✔️ [{len(results)}/{len(video_items)}] {res['title'][:45]} -> {status}")

    if not results:
        print("❌ Nenhum dado coletado.")
        return

    channel_name = results[0].get('uploader') or "Canal"
    save_analysis(channel_name, results)

if __name__ == "__main__":
    main()
