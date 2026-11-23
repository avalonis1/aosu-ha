# Aosu → Home Assistant + Reconnaissance Faciale 100 % Locale

Intégration **Home Assistant** (`custom_components/aosu`) et outils CLI Python pour les caméras **Aosu** (modèles `backend=tuya` comme `V8S`, `C9S`, `L5P`, `C2P` et `backend=self` comme `C2E2D`), **sans abonnement cloud payant** et **sans vider les batteries**.

---

## Fonctionnalités disponibles (Point 1 — Prêt à installer)

* **Custom Component Home Assistant autonome** ([custom_components/aosu](file:///d:/Antigravity/aosu/custom_components/aosu/)) avec **Config Flow** en français :
  * `camera` : dernier snapshot HD de chaque caméra (sans réveiller les caméras sur batterie).
  * `sensor` : **Batterie (%)**, **Signal Wi-Fi**, **Dernier événement** (`person`, `ring`, `stay`), **Dernier visage reconnu** (+ score de confiance).
  * `binary_sensor` : **En ligne**, **Personne détectée**, **Sonnette** (pour la sonnette `V8S`).
  * Événements Home Assistant pour vos automatisations : `aosu_person_detected`, `aosu_doorbell_ring`, `aosu_face_recognized`.
* **Reconnaissance faciale 100 % locale et gratuite** :
  * Dans Home Assistant : connexion directe à un serveur local **CompreFace** (Docker, CPU suffisant) configuré directement depuis l'interface de l'intégration.
  * En CLI local : support **InsightFace** (`faces/<Prenom>/*.jpg` → `python -m aosu.cli faces-index` et `python -m aosu.cli faces-test`).

---

## Installer l'intégration dans Home Assistant

1. Copiez le dossier `custom_components/aosu` dans `/config/custom_components/aosu` sur votre serveur Home Assistant.
2. Redémarrez Home Assistant.
3. Allez dans **Paramètres → Appareils et services → Ajouter une intégration → Aosu Cameras**.
4. Renseignez :
   * Votre **email** et **mot de passe** Aosu (région `eu`).
   * *(Optionnel pour la reconnaissance faciale)* L'URL de votre serveur local **CompreFace** (ex. `http://192.168.1.X:8000`) et sa clé API *Recognition*.

---

## Utilisation du CLI de test local

```powershell
pip install -r requirements.txt

# 1. Connexion & inspection
python -m aosu.cli login --email votre@email.com
python -m aosu.cli devices
python -m aosu.cli events --count 5

# 2. Reconnaissance faciale locale avec InsightFace (optionnel)
pip install insightface onnxruntime opencv-python-headless
# Placez 2-3 photos par personne dans faces/<Prenom>/*.jpg
python -m aosu.cli faces-index
python -m aosu.cli faces-test --count 5
```

---

## Feuille de route

- [x] **Point 1** : API Cloud Aosu + Snapshots HD + Batterie/Wi-Fi + Événements `person`/`ring` + Reconnaissance faciale locale (CompreFace / InsightFace) + Custom Component Home Assistant (`custom_components/aosu`).
- [ ] **Point 2** : Flux vidéo **Live à la demande uniquement** (quand vous cliquez sur la caméra dans HA, sans vider les batteries) via Tuya WebRTC (`V8S`, `C9S`, `L5P`) et Agora RTC (`C2E2D`).
- [ ] **Point 3** : Intégration locale des 2 appareils **SwitchBot** dans Home Assistant (Bluetooth local / Matter, sans cloud).
