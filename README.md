# 🎬 SRT Editor EASY — Version Beta

> **⚠️ Version beta en developpement.**
> Pour l'editeur stable et complet, utilisez le projet original :
>
> ### 🔗 [RDTvlokip/vtt-editor-pro](https://github.com/RDTvlokip/vtt-editor-pro)
> **[→ Essayer en ligne (v3.0)](https://rdtvlokip.github.io/vtt-editor-pro/vtt-editor-pro-v3.0.html)**

---

## 🙏 Merci a RDTvlokip (Theo)

Ce fork repose entierement sur le travail exceptionnel de **Theo (RDTvlokip)**, createur de VTT Editor Pro. Son editeur de sous-titres vanilla JS est une base remarquable — 6900+ lignes, zero framework, tout dans un seul fichier HTML. Ce fork n'existerait pas sans son travail. Merci Theo.

[→ Projet original](https://github.com/RDTvlokip/vtt-editor-pro) | [→ Ko-fi](https://ko-fi.com/rdtvlokip)

---

## En quoi ce fork est different ?

SRT Editor EASY est oriente **correction guidee de SRT issus de transcription automatique** (Whisper, diarisation multi-locuteurs). Il ajoute un serveur Flask et une interface pas-a-pas.

| Feature | Original | Ce fork |
|---------|----------|---------|
| Fonctionnement | Fichier HTML seul | Flask + HTML |
| Persistence | localStorage | Serveur (`uploads/`) |
| Upload audio | Navigateur | Serveur + projet |
| Import SRT | Manuel | Direct sans dropdown |
| Locuteurs | Non | Detection auto + inline |
| Transport | Play/Pause | ⏮ ⏪ ⏯ ⏩ ⏭ 1x/1.5x/2x |
| Debug | Console | Panel lateral + logs serveur |
| Guide utilisateur | Non | Bandeau centre etapes |
| Edition segments | 3 boutons | 5 boutons compacts |
| Auto-pause edition | Non | Oui |

---

## Installation et lancement

```bash
git clone https://github.com/Martossien/vtt-editor-pro-fr-easy.git
cd vtt-editor-pro-fr-easy
pip install flask
./start.sh --port 7861
```

Puis ouvrir `http://localhost:7861`.

---

## Utilisation rapide

1. **1️⃣ Audio** — Uploader le fichier audio/video
2. **2️⃣ SRT** — Importer le fichier SRT (ou VTT, ASS, SBV)
3. **Corriger** — Double-clic sur un segment, ou utiliser les boutons ✏️ 🎤 ⏱️
4. **Exporter** — `💾 Export` → SRT ou VTT

Navigation clavier : `←`/`→` segments, `Entree` valider, `C` couper, `Espace` play/pause.

---

## Scripts de gestion

| Script | Usage |
|--------|-------|
| `./start.sh` | Demarrer le serveur |
| `./stop.sh` | Arreter le serveur |
| `./status.sh` | Etat du serveur + logs |
| `./status.sh --watch` | Monitoring temps reel |
| `./status.sh --logs` | Suivi des logs |

---

## Licence

**CC BY-NC 4.0** — Ce fork conserve la licence originale de RDTvlokip.

---

<div align="center">

### Merci Theo pour ce projet formidable

*Fork beta par Martossien — allez voir l'original* ⭐

</div>
