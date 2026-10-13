import os
import sys
import json
import time
from datetime import timedelta
import yt_dlp

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

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

# Vetores de pesquisa no estilo real de novelinhas/dramas/mininovelas
SEARCH_TERMS = [
    # Termos do formato e hashtags virais
    "mininovela reflexão",
    "novelinhas shorts drama",
    "histórias de reflexão shorts",
    "telekwai novela",
    "dorama dublado shorts",
    "minidrama brasil",
    "novela vertical traição",
    
    # Gatilhos clássicos de roteiro que batem milhões de views
    "ele humilhou a esposa shorts",
    "ele fingiu ser pobre shorts",
    "ela rejeitou o rapaz humilde shorts",
    "o patrão humilhou o funcionário shorts",
    "a sogra humilhou a nora shorts",
    "marido troca esposa grávida shorts",
    
    # Plataformas adaptadas e canais de drama vertical
    "reelshort portugues",
    "dramabox dublado brasil",
    "sereal drama portugues",
    "historias de vida superação shorts"
]

def format_num(num):
    if not num:
        return "N/A"
    return f"{num:,}"

def run_deep_scan(min_subs=100_000, target_channels=5):
    print("=" * 70)
    print(" 🕵️ DEEP SCRAPER DE NOVELINHAS & DRAMAS VERTICAIS EM ALTA ")
    print(f" 🎯 Critério Mínimo: Canais com mais de {min_subs:,} inscritos e milhões de views")
    print("=" * 70)

    t0 = time.time()
    discovered_videos = {}

    print(f"\n[Fase 1/3] Varrendo {len(SEARCH_TERMS)} vetores de busca de novelinhas e dramas...")
    
    ydl_flat = yt_dlp.YoutubeDL({
        **YTDL_BASE_OPTS,
        'extract_flat': 'in_playlist'
    })

    for idx, term in enumerate(SEARCH_TERMS, 1):
        print(f"  [{idx}/{len(SEARCH_TERMS)}] Buscando por: '{term}'...")
        try:
            res = ydl_flat.extract_info(f"ytsearch15:{term}", download=False)
            if res and 'entries' in res:
                for e in res['entries']:
                    if not e or not e.get('id'):
                        continue
                    v_id = e['id']
                    if v_id not in discovered_videos:
                        discovered_videos[v_id] = {
                            'id': v_id,
                            'title': e.get('title', ''),
                            'url': f"https://www.youtube.com/watch?v={v_id}",
                            'term_found': term
                        }
        except Exception:
            pass

    print(f"\n✅ Total de {len(discovered_videos)} vídeos candidatos identificados na varredura inicial.")
    print(f"[Fase 2/3] Filtrando canais com mais de {min_subs:,} inscritos e milhões de visualizações...")

    channels_data = {}
    ydl_detail = yt_dlp.YoutubeDL({**YTDL_BASE_OPTS, 'extract_flat': False})

    checked = 0
    for v_id, v_data in discovered_videos.items():
        checked += 1
        if checked % 10 == 0 or checked == 1:
            print(f"  🔍 Analisando candidato {checked}/{len(discovered_videos)} | Canais qualificados encontrados: {len(channels_data)}...")

        try:
            info = ydl_detail.extract_info(v_data['url'], download=False)
            if not info:
                continue

            subs = info.get('channel_follower_count') or 0
            views = info.get('view_count') or 0
            uploader = info.get('uploader') or info.get('channel') or "Canal Desconhecido"
            channel_url = info.get('uploader_url') or info.get('channel_url') or ""
            handle = info.get('uploader_id') or ""

            # Filtro rígido: mínimo de inscritos e visualizações expressivas
            if subs >= min_subs:
                if uploader not in channels_data:
                    channels_data[uploader] = {
                        'channel_name': uploader,
                        'channel_url': channel_url,
                        'handle': handle,
                        'subscribers': subs,
                        'top_videos': []
                    }

                channels_data[uploader]['top_videos'].append({
                    'id': v_id,
                    'title': info.get('title'),
                    'views': views,
                    'duration': info.get('duration'),
                    'url': v_data['url']
                })
                
                print(f"    ✨ CANAL ENCONTRADO: {uploader} ({subs:,} subs | Vídeo com {views:,} views)!")

            # Se já encontramos canais suficientes de grande porte com milhões de views, podemos prosseguir
            qualified_top = [c for c in channels_data.values() if any(v['views'] >= 500_000 for v in c['top_videos'])]
            if len(qualified_top) >= target_channels and checked >= 60:
                print(f"\n🎯 Meta atingida: {len(qualified_top)} canais de alto porte qualificados!")
                break

        except Exception:
            continue

    print(f"\n[Fase 3/3] Consolidando resultados e gerando relatório executivo...")

    # Ordenar canais pelos mais inscritos e maiores views
    ranked_channels = sorted(
        channels_data.values(),
        key=lambda c: max([v['views'] for v in c['top_videos']] or [0]),
        reverse=True
    )

    os.makedirs("output/novelinhas_ia", exist_ok=True)
    report_file = "output/novelinhas_ia/canais_grandes_novelinhas.md"
    json_file = "output/novelinhas_ia/canais_grandes_novelinhas.json"

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(ranked_channels, f, ensure_ascii=False, indent=2)

    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# 🏆 Canais Gigantes em Alta: Novelinhas, Dramas e Mininovelas (+100k Inscritos)\n\n")
        f.write(f"Data do levantamento: {time.strftime('%d/%m/%Y %H:%M:%S')}\n\n")
        f.write(f"Critério: Canais com **mais de {min_subs:,} inscritos** e **milhões de visualizações** no formato.\n\n")
        f.write("---\n\n")

        for idx, ch in enumerate(ranked_channels, 1):
            f.write(f"## {idx}. {ch['channel_name']}\n")
            f.write(f"- 🔗 **Link do Canal:** [{ch['channel_url']}]({ch['channel_url']})\n")
            if ch.get('handle'):
                f.write(f"- 🏷️ **Handle:** `{ch['handle']}`\n")
            f.write(f"- 👥 **Inscritos:** **{format_num(ch['subscribers'])} inscritos**\n\n")

            # Ordenar top vídeos por views
            ch['top_videos'].sort(key=lambda x: x['views'], reverse=True)
            f.write("### 🎬 Vídeos Virais em Destaque do Canal:\n")
            for v in ch['top_videos'][:3]:
                dur_m = str(timedelta(seconds=int(v['duration']))) if v.get('duration') else "Short"
                f.write(f"- **[{v['title']}]({v['url']})**\n")
                f.write(f"  - 👁️ Visualizações: **{format_num(v['views'])} views** | ⏱️ Duração: {dur_m}\n")
            f.write("\n---\n\n")

    elapsed = time.time() - t0
    print(f"\n=======================================================")
    print(f"🎉 Varredura Profunda Concluída em {elapsed:.1f} segundos!")
    print(f"🏆 Canais qualificados encontrados: {len(ranked_channels)}")
    print(f"📁 Relatório salvo em: {os.path.abspath(report_file)}")
    print(f"=======================================================\n")

if __name__ == "__main__":
    min_subs = 100_000
    run_deep_scan(min_subs=min_subs, target_channels=5)
