# 🚧 SRT Editor Pro — Fork en construction

> **Ce dépôt est un fork en cours de développement.**
> Pour utiliser la version stable et complète, rendez-vous sur le projet original :
>
> ### 🔗 [RDTvlokip/vtt-editor-pro](https://github.com/RDTvlokip/vtt-editor-pro)
>
> **[Essayer en ligne → vtt-editor-pro-v3.0.html](https://rdtvlokip.github.io/vtt-editor-pro/vtt-editor-pro-v3.0.html)**

---

## En quoi ce fork est différent ?

Ce fork (`Martossien/vtt-editor-pro-fr-easy`) ajoute :

- **Mode correction guidée** : workflow pas à pas (audio → SRT → corriger → exporter)
- **Gestion multi-locuteurs** : renommage, couleurs, badge inline par segment
- **Serveur Flask intégré** : persistence côté serveur, projets dans `uploads/`
- **Panel Debug** : logs API, événements JS, logs serveur en temps réel
- **Raccourcis additionnels** : `→`/`←` navigation segments, `Entrée` valider+suivant, `C` couper
- **Ajustements fins** : boutons ±100ms, ±500ms, ±1s sur les timecodes
- **Interface en français**

## Lancer le fork

```bash
git clone https://github.com/Martossien/vtt-editor-pro-fr-easy.git
cd vtt-editor-pro-fr-easy
pip install flask
./start.sh --port 7861
```

Puis ouvrir `http://localhost:7861`

---

**Auteur original** : [RDTvlokip (Théo)](https://github.com/RDTvlokip) — [CC BY-NC 4.0](LICENSE.md)
