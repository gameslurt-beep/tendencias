# 🎯 Viral Radar & Content Reverse Engineering Hub

Um hub completo em Python para pesquisa de tendências, engenharia reversa de vídeos e análise profunda de comentários no **YouTube**, **TikTok** e **Reddit**.

## 🚀 Funcionalidades

- **Raio-X de Comentários (YouTube & TikTok):** Extração de comentários em massa com categorização de sentimento, detecção de debates emergentes (sociais, políticos, econômicos), timestamps de cenas marcantes e palpites da audiência.
- **Transcrição e Engenharia Reversa:** Extração ultra-rápida de metadados e transcrições completas do YouTube (Vídeos, Canais e Shorts) em ~4 segundos.
- **Análise de Ganchos (Hooks):** Isola automaticamente os primeiros 30-35 segundos de fala de cada vídeo para estudo de retenção.
- **Explorador de Nichos no YouTube:** Descubra os vídeos com mais visualizações e os canais dominantes em qualquer tema.
- **Radar de Tendências do Reddit:** Monitore dúvidas e tópicos em alta em qualquer subreddit com proteção anti-bloqueio.
- **Máquina Cruzada de Conteúdo:** Conecte as dúvidas do Reddit aos vídeos de maior audiência do YouTube para modelar conteúdo viral.

## 📦 Instalação

```bash
git clone https://github.com/gameslurt-beep/tendencias.git
cd tendencias
pip install -r requirements.txt
python -m playwright install chromium
```

## 🛠️ Como Usar

Basta executar o menu interativo:

```bash
python hub.py
```
