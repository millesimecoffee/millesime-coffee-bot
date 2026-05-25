"""
Script one-shot : migre orders.json + blacklist.json existants vers Supabase.
Lance-le UNE FOIS après avoir créé le schéma SQL.

Usage :
    SUPABASE_URL=https://xxxx.supabase.co SUPABASE_KEY=... python migrate_to_supabase.py

Idempotent : UPSERT sur la clé primaire — relancer ne crée pas de doublons.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent

# Vérifier que les env vars sont là AVANT d'importer le client
if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
    print("❌ SUPABASE_URL et SUPABASE_KEY doivent être définis dans l'environnement")
    print("   Exemple :")
    print("     $env:SUPABASE_URL='https://xxxx.supabase.co'")
    print("     $env:SUPABASE_KEY='eyJ...'")
    sys.exit(1)

import supabase_client as sb


def _to_utc_iso(naive_iso: str) -> str:
    """Convertit '2026-05-22T08:24:38' (naïf) → '2026-05-22T08:24:38+00:00'."""
    try:
        dt = datetime.fromisoformat(naive_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except (ValueError, TypeError):
        return datetime.now(timezone.utc).isoformat()


def migrate_orders():
    src = ROOT / "orders.json"
    if not src.exists():
        print("⏭️  orders.json absent — rien à migrer.")
        return

    with src.open("r", encoding="utf-8") as f:
        orders = json.load(f)

    print(f"📦 {len(orders)} commande(s) à migrer…")
    ok = skipped = failed = 0

    for o in orders:
        oid = o.get("order_id")
        if not oid:
            print(f"   ⏭️  Pas d'order_id — ignoré : {o!r}")
            skipped += 1
            continue
        try:
            row = {
                "id":         oid,
                "user_id":    int(o.get("user_id") or 0),
                "created_at": _to_utc_iso(o.get("created_at", "")),
                "data":       o,
            }
            res = sb.upsert("orders", row, on_conflict="id")
            if res:
                ok += 1
                print(f"   ✅ {oid}")
            else:
                failed += 1
                print(f"   ❌ {oid} — upsert n'a rien retourné")
        except Exception as exc:
            failed += 1
            print(f"   ❌ {oid} — {exc}")

    print(f"\n📦 Commandes : ok={ok}  skipped={skipped}  failed={failed}")


def migrate_blacklist():
    src = ROOT / "blacklist.json"
    if not src.exists():
        print("⏭️  blacklist.json absent — rien à migrer.")
        return
    try:
        with src.open("r", encoding="utf-8") as f:
            uids = json.load(f)
    except Exception as exc:
        print(f"❌ Lecture blacklist.json : {exc}")
        return

    print(f"\n🚫 {len(uids)} utilisateur(s) bannis à migrer…")
    ok = failed = 0
    for uid in uids:
        try:
            sb.upsert("blacklist", {"user_id": int(uid)}, on_conflict="user_id")
            ok += 1
        except Exception as exc:
            failed += 1
            print(f"   ❌ uid={uid} — {exc}")
    print(f"🚫 Blacklist : ok={ok}  failed={failed}")


def main():
    if not sb.is_enabled():
        print("❌ Supabase non configuré — abandon.")
        sys.exit(1)

    print(f"🔗 Cible : {os.getenv('SUPABASE_URL')}")
    print("─" * 60)
    migrate_orders()
    migrate_blacklist()
    print("─" * 60)
    print("✅ Migration terminée.")


if __name__ == "__main__":
    main()
