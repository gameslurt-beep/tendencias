import os
import sys
import json
import re
import time
from collections import Counter
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

# ==============================================================================
# DICIONÁRIOS SEMÂNTICOS PARA ANÁLISE DE SENTIMENTO E TEMAS DO MUNDO REAL
# ==============================================================================

TEMAS_SOCIAIS = {
    'Economia, Dinheiro e Trabalho': [
        'dinheiro', 'trabalho', 'salário', 'pobre', 'rico', 'emprego', 'patrão', 
        'pagar', 'crise', 'milionário', 'ouro', 'herança', 'chefe', 'salario',
        'humilde', 'banco', 'dívida', 'divida', 'empresário', 'empresa', 'custo'
    ],
    'Família e Relacionamentos': [
        'mãe', 'mae', 'pai', 'filho', 'filha', 'família', 'familia', 'marido', 
        'esposa', 'namorado', 'namorada', 'traição', 'traicao', 'casamento', 
        'sogra', 'nora', 'irmão', 'irmao', 'divórcio', 'divorcio', 'amante'
    ],
    'Justiça, Leis e Sociedade': [
        'lei', 'leis', 'crime', 'justiça', 'justica', 'polícia', 'policia', 
        'processo', 'prisão', 'prisao', 'cadeia', 'direitos', 'sociedade', 
        'denúncia', 'denuncia', 'advogado', 'juiz', 'tribunal', 'golpe'
    ],
    'Moral, Caráter e Fé': [
        'deus', 'caráter', 'carater', 'humildade', 'vergonha', 'ingrato', 
        'ingratidão', 'lição', 'licao', 'coração', 'coracao', 'maldade', 
        'castigo', 'orgulho', 'respeito', 'fé', 'fe', 'ganância', 'ganancia'
    ]
}

SENTIMENTOS = {
    'Indignação Moral / Revolta': [
        'ódio', 'odio', 'raiva', 'absurdo', 'revoltante', 'nojo', 'canalha', 
        'covarde', 'humilhação', 'humilhacao', 'safado', 'falsa', 'falso', 
        'nojento', 'nojenta', 'vergonha', 'ridículo', 'ridiculo', 'injusto'
    ],
    'Catarse / Justiça Merecida': [
        'bem feito', 'mereceu', 'satisfação', 'satisfacao', 'tomou', 'castigo', 
        'vingança', 'vinganca', 'justiça', 'fez bem', 'aprendeu', 'levou'
    ],
    'Empatia / Emoção Real': [
        'chorei', 'emocionante', 'triste', 'lágrimas', 'lagrimas', 'lindo', 
        'linda', 'arrepiei', 'dor', 'doeu', 'emocionei', 'emocionou'
    ],
    'Dúvidas / Curiosidade': [
        'por que', 'pq', 'por quê', 'quem é', 'qual o nome', 'como assim', 
        'não entendi', 'nao entendi', 'cadê', 'cade', 'onde', 'alguém explica', '?'
    ],
    'Humor / Sarcasmo': [
        'kkk', 'haha', 'rindo', 'morri', 'engraçado', 'engracado', 'piada', 
        'meme', 'rir', 'gargalhada', '😂', '🤣', '😭'
    ]
}

PALPITES_DIRETOR_PADROES = [
    r'se fosse eu\b',
    r'eu teria\b',
    r'ele deveria\b',
    r'ela deveria\b',
    r'o certo era\b',
    r'tinha que ter\b',
    r'deveria ter feito\b',
    r'se eu fosse\b',
    r'não devia\b',
    r'nao devia\b',
    r'deveria ter falado\b',
    r'bem que podia\b'
]

# ==============================================================================
# MOTOR DE EXTRAÇÃO E PROCESSAMENTO
# ==============================================================================

def extract_comments_youtube(video_url: str, max_comments: int = 150):
    """Extrai comentários de qualquer vídeo do YouTube com contagem de likes e autor."""
    print(f"\n🔍 Conectando e extraindo comentários de: {video_url}...")
    ydl_opts = {
        **YTDL_BASE_OPTS,
        'getcomments': True,
        'max_comments': max_comments
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if not info:
                print("❌ Não foi possível carregar o vídeo.")
                return None, []

            comments_raw = info.get('comments', [])
            title = info.get('title', 'Vídeo')
            uploader = info.get('uploader') or info.get('channel') or 'Canal'

            processed = []
            for c in comments_raw:
                text = c.get('text', '').strip()
                if not text:
                    continue
                processed.append({
                    'id': c.get('id'),
                    'author': c.get('author') or '@anônimo',
                    'text': text,
                    'likes': c.get('like_count') or 0,
                    'timestamp': c.get('timestamp')
                })

            print(f"✅ {len(processed)} comentários extraídos com sucesso!")
            return {'title': title, 'uploader': uploader, 'url': video_url}, processed

    except Exception as e:
        print(f"❌ Erro na extração de comentários: {e}")
        return None, []

def analyze_comments(video_meta: dict, comments: list):
    """Processa o mapa semântico, sentimentos, timestamps, palpites e debates sociais."""
    if not comments:
        return None

    total_comments = len(comments)
    total_likes = sum(c['likes'] for c in comments)

    # 1. Timestamps e Citações Marcantes
    timestamp_regex = re.compile(r'\b([0-5]?\d:[0-5]\d)\b')
    timestamps_found = Counter()
    timestamps_likes = Counter()

    # 2. Palpites de "Diretores de Sofá"
    palpites = []

    # 3. Mapeamento de Temas do Mundo Real
    temas_score = {k: 0 for k in TEMAS_SOCIAIS}
    temas_likes = {k: 0 for k in TEMAS_SOCIAIS}
    temas_exemplos = {k: [] for k in TEMAS_SOCIAIS}

    # 4. Matriz de Sentimento
    sentimentos_score = {k: 0 for k in SENTIMENTOS}
    sentimentos_likes = {k: 0 for k in SENTIMENTOS}

    for c in comments:
        text = c['text']
        text_lower = text.lower()
        likes = c['likes']

        # Verificar Timestamps
        ts_matches = timestamp_regex.findall(text)
        for ts in ts_matches:
            timestamps_found[ts] += 1
            timestamps_likes[ts] += (likes + 1)

        # Verificar Palpites
        for pat in PALPITES_DIRETOR_PADROES:
            if re.search(pat, text_lower):
                palpites.append(c)
                break

        # Pontuar Temas Sociais
        for tema, palavras in TEMAS_SOCIAIS.items():
            if any(p in text_lower for p in palavras):
                temas_score[tema] += 1
                temas_likes[tema] += (likes + 1)
                if len(temas_exemplos[tema]) < 3:
                    temas_exemplos[tema].append(c)

        # Pontuar Sentimentos
        for sent, palavras in SENTIMENTOS.items():
            if any(p in text_lower for p in palavras):
                sentimentos_score[sent] += 1
                sentimentos_likes[sent] += (likes + 1)

    # Ordenar palpites por likes
    palpites.sort(key=lambda x: x['likes'], reverse=True)

    # Top Comentários Globais (a voz da maioria)
    top_comments = sorted(comments, key=lambda x: x['likes'], reverse=True)[:5]

    return {
        'meta': video_meta,
        'total_comments': total_comments,
        'total_likes': total_likes,
        'top_comments': top_comments,
        'timestamps': timestamps_found.most_common(5),
        'timestamps_likes': timestamps_likes,
        'palpites': palpites[:5],
        'temas_score': temas_score,
        'temas_likes': temas_likes,
        'temas_exemplos': temas_exemplos,
        'sentimentos_score': sentimentos_score,
        'sentimentos_likes': sentimentos_likes
    }

def generate_report(analysis: dict, output_dir: str = "output/comentarios"):
    """Gera o relatório executivo da análise de comentários em Markdown."""
    os.makedirs(output_dir, exist_ok=True)
    meta = analysis['meta']
    slug = re.sub(r'[^a-zA-Z0-9_-]', '_', meta['title'])[:40].strip('_') or "video"

    report_path = os.path.join(output_dir, f"analise_sentimento_{slug}.md")
    json_path = os.path.join(output_dir, f"dados_comentarios_{slug}.json")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# 🧭 Raio-X de Sentimento e Debates da Audiência\n\n")
        f.write(f"- 🎬 **Vídeo:** [{meta['title']}]({meta['url']})\n")
        f.write(f"- 👤 **Canal:** {meta['uploader']}\n")
        f.write(f"- 💬 **Comentários Analisados:** {analysis['total_comments']}\n")
        f.write(f"- 👍 **Curtidas Somadas nos Comentários:** {analysis['total_likes']:,}\n")
        f.write(f"- 📅 **Data da Análise:** {time.strftime('%d/%m/%Y %H:%M:%S')}\n\n")
        f.write("---\n\n")

        # 1. Pulso Emocional Geral
        f.write("## 🌡️ 1. Pulso Emocional da Audiência (O que as pessoas SENTIRAM)\n\n")
        total_sent = sum(analysis['sentimentos_score'].values()) or 1
        sorted_sent = sorted(analysis['sentimentos_score'].items(), key=lambda x: x[1], reverse=True)
        for s_name, count in sorted_sent:
            pct = (count / total_sent) * 100
            likes_s = analysis['sentimentos_likes'].get(s_name, 0)
            f.write(f"- **{s_name}:** {pct:.1f}% das reações identificadas ({likes_s:,} curtidas somadas)\n")
        f.write("\n---\n\n")

        # 2. Debates Emergentes e Temas do Mundo Real
        f.write("## 🌍 2. Debates Sociais Emergentes (Para onde a discussão migrou)\n\n")
        sorted_temas = sorted(analysis['temas_likes'].items(), key=lambda x: x[1], reverse=True)
        for tema, l_count in sorted_temas:
            mentions = analysis['temas_score'].get(tema, 0)
            if mentions > 0:
                f.write(f"### 📌 {tema}\n")
                f.write(f"- Impacto: **{l_count:,} curtidas somadas** em {mentions} comentários.\n")
                exemplos = analysis['temas_exemplos'].get(tema, [])
                for ex in exemplos[:2]:
                    f.write(f"  > *\"{ex['text']}\"* — **{ex['author']}** ({ex['likes']} likes)\n")
                f.write("\n")
        f.write("---\n\n")

        # 3. Momentos de Pico e Cenas Marcantes
        f.write("## ⏱️ 3. A Cena Mais Marcante (Momentos exatos citados pela audiência)\n\n")
        if analysis['timestamps']:
            for ts, count in analysis['timestamps']:
                l_ts = analysis['timestamps_likes'].get(ts, 0)
                f.write(f"- **Minuto {ts}:** Citado em {count} comentários ({l_ts:,} curtidas somadas nas menções)\n")
        else:
            f.write("*Nenhum timestamp específico com minutos/segundos foi citado explicitamente nos comentários analisados.*\n")
        f.write("\n---\n\n")

        # 4. Palpites e Projeções do Público ("Diretores de Sofá")
        f.write("## 🧐 4. Projeções e Conselhos da Audiência (\"Se fosse eu...\")\n\n")
        if analysis['palpites']:
            for p in analysis['palpites']:
                f.write(f"- 👍 **{p['likes']} curtidas** | **{p['author']}:**\n")
                f.write(f"  > *\"{p['text']}\"*\n\n")
        else:
            f.write("*O público não fez projeções diretas em primeira pessoa nesta amostragem.*\n\n")
        f.write("---\n\n")

        # 5. A Voz da Maioria (Top Comentários)
        f.write("## 🏆 5. Comentários Mais Curtidos (A Opinião da Maioria)\n\n")
        for idx, c in enumerate(analysis['top_comments'], 1):
            f.write(f"### {idx}. {c['author']} ({c['likes']:,} curtidas)\n")
            f.write(f"> *\"{c['text']}\"*\n\n")

    print(f"\n=======================================================")
    print(f"🎉 Análise Estratégica de Comentários Concluída!")
    print(f"📁 Relatório Markdown: {os.path.abspath(report_path)}")
    print(f"📁 Dados Estruturados: {os.path.abspath(json_path)}")
    print(f"=======================================================\n")
    return report_path

def run_comment_pipeline(video_url: str, max_comments: int = 150):
    meta, comments = extract_comments_youtube(video_url, max_comments=max_comments)
    if not comments:
        print("❌ Nenhum comentário disponível para análise.")
        return None
    analysis = analyze_comments(meta, comments)
    return generate_report(analysis)

if __name__ == "__main__":
    url_in = sys.argv[1] if len(sys.argv) > 1 else input("👉 Digite a URL do vídeo para analisar os comentários: ").strip()
    if url_in:
        run_comment_pipeline(url_in)
