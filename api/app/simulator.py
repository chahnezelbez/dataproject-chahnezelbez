"""Simulateur de capteurs : envoie des mesures JSON dans Kafka.

Utilisation :
    python -m app.simulator --count 30 --interval 1

Envoie 30 messages (un tour de 3 salles par seconde). Dans chaque bloc de 10,
le 5e est invalide et le 10e est un doublon. Il faut donc 24 valides, 3 invalides, 3 doublons.
"""
import argparse
import json
import logging
import time
from datetime import datetime, timezone

from confluent_kafka import Producer

TOPIC = "campus.measurements"
ROOMS = ["A101", "A102", "B201"]

log = logging.getLogger("simulator")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=30, help="Nombre de messages à envoyer")
    parser.add_argument("--interval", type=float, default=1.0, help="Intervalle en secondes")
    parser.add_argument("--bootstrap", default="127.0.0.1:9092", help="Serveur Kafka")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    
    producer = Producer({"bootstrap.servers": args.bootstrap})
    log.info("sending to %s, topic %s, one round every %s s", args.bootstrap, TOPIC, args.interval)

    now = datetime.now(timezone.utc).isoformat()

    for i in range(1, args.count + 1):
        room = ROOMS[(i - 1) % 3]
        
        # Logique des anomalies : le 5e est invalide, le 10e est un doublon
        if i % 10 == 5:
            data = {"room": room, "measured_at": now, "co2_ppm": -1, "temperature_c": 20.0, "humidity_pct": 50.0}
            log.info("message %s -> %s: invalid (Invalid co2_ppm)", i, room)
        elif i % 10 == 0:
            # On renvoie exactement le message précédent (le 9e)
            data = {"room": ROOMS[(i - 2) % 3], "measured_at": now, "co2_ppm": 600, "temperature_c": 20.0, "humidity_pct": 50.0}
            log.info("message %s -> %s: duplicate", i, room)
        else:
            data = {"room": room, "measured_at": now, "co2_ppm": 600 + i, "temperature_c": 20.0 + (i % 5), "humidity_pct": 45.0 + (i % 10)}
            log.info("message %s -> %s: valid", i, room)

        # Envoi du message (la clé est la salle, pour choisir la partition)
        producer.produce(TOPIC, key=room.encode("utf-8"), value=json.dumps(data).encode("utf-8"))
        producer.poll(0)
        
        time.sleep(args.interval)

    producer.flush()
    log.info("all messages confirmed by Kafka")


if __name__ == "__main__":
    main()
