<table>
  <tr>
    <td width="25%" align="left" valign="middle">
      <img src="assets/CAC-logo.png" alt="Codex Audio Companion" width="100%">
    </td>
    <td width="75%" align="center" valign="middle">
      <h1>Codex Audio Companion</h1>
      <p><strong>Reste dans ton flow, Codex te parle.</strong></p>
      <p>
	<img src="https://img.shields.io/github/v/release/TREHAND-Christian/codex-audio-companion">
        <img src="https://img.shields.io/badge/python-3.12-blue">
        <img src="https://img.shields.io/badge/platform-Windows-lightgrey">
        <img src="https://img.shields.io/badge/status-experimental-orange">
      </p>
    </td>
  </tr>
</table>


Codex Audio Companion est une application desktop qui transforme les réponses de **Codex (extension OpenAI pour VS Code)** en lecture audio claire et immédiate.

Pensée comme un compagnon discret, elle fonctionne entièrement en local, sans plugin VS Code supplémentaire ni accès réseau pour la lecture vocale.

---

## ✨ Fonctionnalités

- 🔊 Lecture vocale automatique (TTS Windows – WinRT)
- 👀 Surveillance en temps réel des sessions Codex (`.jsonl`)
- 🎛️ Mini-barre flottante (Play / Pause / Stop / Mute)
- 🧷 Icône dans la zone de notification
- 🌍 Traduction optionnelle
- 🪟 Fenêtre dédiée texte / traduction
- ⚙️ Paramètres complets sauvegardés automatiquement
- 🧠 Anti-doublon intelligent
- 💤 Fonctionnement en arrière-plan

---

## 🧩 Comment ça fonctionne

1. Codex génère une réponse dans VS Code
2. Le fichier de session `.jsonl` est surveillé
3. La nouvelle réponse est détectée, affichée et lue

➡️ Aucun plugin VS Code supplémentaire
➡️ Aucun accès réseau requis

---

## 🖥️ Pré-requis

- Windows 10 / 11
- Python **3.12**
- Extension **Codex OpenAI’s** pour VS Code
- Voix Windows OneCore installées

---

## 🚀 Installation

```bash
pip install -r requirements.txt
```

Lancer l’application :

```bash
python -m app.run_with_watcher
```

---

## 🎯 Cas d’usage

- Continuer à coder pendant l’écoute
- Réduire la fatigue visuelle
- Multitâche (debug, refacto, doc)

---

## 🧠 Philosophie

Un **copilote discret**, toujours prêt mais jamais intrusif.
Le code reste au centre.

---

## 📦 Releases

Voir l’onglet **Releases** GitHub pour les versions publiées.

---

## 📜 Licence

Projet personnel / expérimental.
