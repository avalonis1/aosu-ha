"""Interactive CLI Proof-of-Concept for Aosu Cloud REST, AWS IoT MQTT, and Agora tokens."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from .client import AosuClient
from .face_recognition import InsightFaceRecognizer
from .mqtt import AosuMqttListener

DEFAULT_SESSION_FILE = Path(".aosu_session.json")


def _load_client(session_file: Path) -> AosuClient:
    if not session_file.exists():
        print(
            f"Session file '{session_file}' not found. Run 'python -m aosu.cli login' first.",
            file=sys.stderr,
        )
        sys.exit(1)
    return AosuClient.from_session_file(session_file)


def cmd_login(args: argparse.Namespace) -> None:
    email = args.email or input("Email Aosu : ").strip()
    password = args.password or getpass.getpass("Mot de passe Aosu : ")
    with AosuClient(region=args.region) as client:
        session = client.login(
            email=email,
            password=password,
            region=args.region,
            country_code=args.country_code,
            country_abbr=args.country_abbr,
        )
        client.save_session(args.session)
        print(
            f"Connexion réussie ! uid={session.uid} region={session.region} "
            f"(session enregistrée dans {args.session})"
        )


def cmd_devices(args: argparse.Namespace) -> None:
    with _load_client(args.session) as client:
        devices = client.get_devices()
        if not devices:
            print("Aucune caméra trouvée sur ce compte.")
            return
        print(f"{len(devices)} appareil(s) trouvé(s) :")
        for d in devices:
            bat = f"{d.battery}%" if d.battery is not None else "secteur/N/A"
            print(
                f"  - {d.title} | sn={d.sn} | model={d.model} | "
                f"backend={d.svc_type or '?'} | online={d.online} | battery={bat}"
            )
        if args.raw:
            print("\n=== JSON brut ===")
            print(json.dumps([d.raw for d in devices], indent=2, ensure_ascii=False))


def cmd_events(args: argparse.Namespace) -> None:
    with _load_client(args.session) as client:
        sns = args.sn or [d.sn for d in client.get_devices() if d.online]
        events = client.get_image_events(sns, count=args.count)
        print(f"{len(events)} événement(s) snapshot récent(s) :")
        for ev in events:
            print(
                f"  - sn={ev.sn} | time={ev.event_time} | type={ev.event_type} | "
                f"has_image={bool(ev.image_url)}"
            )
        if args.raw:
            print(json.dumps([e.raw for e in events], indent=2, ensure_ascii=False))


def cmd_agora(args: argparse.Namespace) -> None:
    with _load_client(args.session) as client:
        sns = args.sn or [d.sn for d in client.get_devices()]
        info = client.get_play_info(sns)
        print(f"Agora AppID : {info.app_id}")
        print(f"Expiration  : {info.expiration}")
        for ch in info.channels:
            enc_mode = "AES-128-GCM2" if ch.enc_kdf_salt else ("AES-128-GCM" if ch.enc_key else "none")
            print(
                f"  - sn={ch.device_id} | channel={ch.dev_rtc_channel} | "
                f"rtm_uid={ch.dev_rtm_uid} | encryption={enc_mode}"
            )


def cmd_wakeup(args: argparse.Namespace) -> None:
    with _load_client(args.session) as client:
        res = client.wakeup_device(args.sn)
        print(json.dumps(res, indent=2, ensure_ascii=False))


def cmd_mqtt(args: argparse.Namespace) -> None:
    with _load_client(args.session) as client:
        sns = args.sn or [d.sn for d in client.get_devices()]
        auth_list = client.get_mqtt_auth(sns)
        if not auth_list:
            print("Aucune configuration AWS MQTT retournée par le serveur.", file=sys.stderr)
            sys.exit(1)
        auth = auth_list[0]
        print(f"Endpoint AWS IoT : {auth.endpoint} (region={auth.region})")
        print(f"Client ID        : {auth.client_id}")
        print(f"Appareils        : {[d.device_id for d in auth.devices]}")

    def _handle(topic: str, payload: dict | str) -> None:
        print(f"\n[EVENT] topic={topic}")
        if isinstance(payload, dict):
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(payload)

    listener = AosuMqttListener(auth, on_message=_handle)
    try:
        listener.run_forever()
    except KeyboardInterrupt:
        print("\nArrêt de l'écoute MQTT.")


def cmd_faces_index(args: argparse.Namespace) -> None:
    rec = InsightFaceRecognizer(faces_dir=args.faces_dir, index_file=args.index)
    counts = rec.build_index()
    if not counts:
        print(
            f"Aucun visage indexé. Ajoutez des photos dans '{args.faces_dir}/<Prenom>/*.jpg' puis relancez."
        )
        return
    print(f"Index local enregistré dans '{args.index}' :")
    for name, n in counts.items():
        print(f"  - {name}: {n} photo(s)")


def cmd_faces_test(args: argparse.Namespace) -> None:
    rec = InsightFaceRecognizer(
        faces_dir=args.faces_dir,
        index_file=args.index,
        threshold=args.threshold,
    )
    rec.load_or_build_index()
    with _load_client(args.session) as client:
        sns = [args.sn] if args.sn else [d.sn for d in client.get_devices() if d.online]
        events = client.get_image_events(sns, count=args.count)
        for ev in events:
            if not ev.image_url:
                continue
            img = client.download_image(ev.image_url)
            matches = rec.recognize_bytes(img)
            names = [f"{m.name} ({m.confidence:.0%})" for m in matches] or ["Aucun visage détecté"]
            print(f"  - sn={ev.sn} | time={ev.event_time} | type={ev.event_type} -> {', '.join(names)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Aosu Cloud & AWS IoT MQTT CLI (PoC)")
    parser.add_argument(
        "--session",
        type=Path,
        default=DEFAULT_SESSION_FILE,
        help="Chemin du fichier de session (défaut: .aosu_session.json)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("login", help="Se connecter au compte Aosu")
    p_login.add_argument("--email", help="Email du compte Aosu")
    p_login.add_argument("--password", help="Mot de passe (demandé de façon masquée si omis)")
    p_login.add_argument("--region", default="eu", choices=["eu", "us", "ap", "cn"])
    p_login.add_argument("--country-code", default="33")
    p_login.add_argument("--country-abbr", default="FR")
    p_login.set_defaults(func=cmd_login)

    p_dev = sub.add_parser("devices", help="Lister les caméras du compte")
    p_dev.add_argument("--raw", action="store_true", help="Afficher le JSON brut complet")
    p_dev.set_defaults(func=cmd_devices)

    p_ev = sub.add_parser("events", help="Afficher les détections récentes")
    p_ev.add_argument("--sn", nargs="*", help="Numéro(s) de série")
    p_ev.add_argument("--count", type=int, default=10)
    p_ev.add_argument("--hours", type=int, default=24)
    p_ev.add_argument("--raw", action="store_true")
    p_ev.set_defaults(func=cmd_events)

    p_ag = sub.add_parser("agora", help="Vérifier les tokens Agora RTC/RTM")
    p_ag.add_argument("--sn", nargs="*", help="Numéro(s) de série")
    p_ag.set_defaults(func=cmd_agora)

    p_wk = sub.add_parser("wakeup", help="Réveiller une caméra sur batterie")
    p_wk.add_argument("sn", help="Numéro de série de la caméra")
    p_wk.set_defaults(func=cmd_wakeup)

    p_mq = sub.add_parser("mqtt", help="Écouter les événements temps réel via AWS IoT MQTT")
    p_mq.add_argument("--sn", nargs="*", help="Numéro(s) de série")
    p_mq.set_defaults(func=cmd_mqtt)

    p_fi = sub.add_parser("faces-index", help="Indexer les visages connus depuis faces/<Prenom>/*.jpg")
    p_fi.add_argument("--faces-dir", default="faces")
    p_fi.add_argument("--index", default="faces_index.json")
    p_fi.set_defaults(func=cmd_faces_index)

    p_ft = sub.add_parser("faces-test", help="Tester la reconnaissance faciale locale sur les derniers snapshots")
    p_ft.add_argument("--sn", help="Numéro de série d'une caméra précise")
    p_ft.add_argument("--count", type=int, default=3)
    p_ft.add_argument("--faces-dir", default="faces")
    p_ft.add_argument("--index", default="faces_index.json")
    p_ft.add_argument("--threshold", type=float, default=0.45)
    p_ft.set_defaults(func=cmd_faces_test)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
