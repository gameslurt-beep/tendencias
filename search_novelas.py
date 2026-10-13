import os
import sys
import json
import time
import yt_dlp
import hub

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

# Buscas estratégicas focadas no formato de ficção/novelinhas feitas com IA
search_terms = [
    "novelinha inteligência artificial",
    "novela feita com inteligência artificial",
    "mini novela com IA shorts",
    "novelinha IA drama",
    "BOQUENILCE FLIX novela"
]

ydl = yt_dlp.YoutubeDL({
    'extractor_args': {'youtube': {'player_client': ['android']}},
    'quiet': True,
    'extract_flat': 'in_playlist'
})

collected = {}

t0 = time.time()
print("🔍 Rastreador de Novelinhas com IA ativado...")

for term in search_terms:
    res = ydl.extract_info(f"ytsearch6:{term}", download=False)
    for e in res.get('entries', []):
        if not e:
            continue
        v_id = e.get('id')
        title = e.get('title', '')
        views = e.get('view_count') or 0
        
        # Filtro para ignorar tutoriais técnicos e priorizar a ficção/novela
        ignore_words = ["como criar", "tutorial", "como fazer", "passo a passo", "aprenda a", "criei um canal", "ferramentas de ia"]
        if any(w in title.lower() for w in ignore_words):
            continue
            
        if v_id not in collected:
            collected[v_id] = {
                'id': v_id,
                'title': title,
                'views': views,
                'uploader': e.get('uploader') or e.get('channel') or "Canal",
                'duration': e.get('duration'),
                'url': f"https://www.youtube.com/watch?v={v_id}"
            }

# Ordenar pelas maiores visualizações
top_5 = sorted(collected.values(), key=lambda x: x['views'], reverse=True)[:5]

print(f"\n⚡ Top 5 selecionados em {time.time()-t0:.2f}s. Extraindo ganchos e transcrições em paralelo...")

# Extrair metadados e ganchos em paralelo
results = []
for item in top_5:
    processed = hub.process_single_video(item['url'])
    if processed:
        results.append(processed)
    else:
        results.append(item)

# Salvar relatório no output
os.makedirs("output/novelinhas_ia", exist_ok=True)
report_path = "output/novelinhas_ia/top_5_novelinhas_ia.md"
json_path = "output/novelinhas_ia/dados_novelinhas_ia.json"

with open(json_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

with open(report_path, "w", encoding="utf-8") as f:
    f.write("# 🎭 Top 5 Novelinhas em Alta com Inteligência Artificial no YouTube\n\n")
    f.write(f"Data da análise: {time.strftime('%d/%m/%Y %H:%M:%S')}\n\n")
    f.write("---\n\n")
    
    for idx, v in enumerate(results, 1):
        f.write(f"### {idx}. {v['title']}\n")
        f.write(f"- 👤 **Canal:** {v.get('uploader', 'N/A')}\n")
        views_str = f"{v['views']:,}" if 'views' in v and v['views'] else (f"{v.get('view_count', 0):,}" if v.get('view_count') else "N/A")
        f.write(f"- 👁️ **Visualizações:** {views_str}\n")
        dur_str = hub.format_duration(v.get('duration'))
        f.write(f"- ⏱️ **Duração:** {dur_str}\n")
        f.write(f"- 🔗 **Link:** [{v['url']}]({v['url']})\n")
        
        t = v.get('transcript')
        if t and t.get('hook_text'):
            f.write(f"\n> **🎣 Gancho Inicial (Primeiros 30s):**\n")
            f.write(f"> *\"{t['hook_text']}\"*\n\n")
        else:
            f.write("\n⚠️ *Transcrição indisponível ou sem legenda direta.*\n\n")
        f.write("---\n\n")

print(f"\n🎉 Relatório gerado em {time.time()-t0:.2f}s!")
print(f"📁 Relatório: {os.path.abspath(report_path)}")
