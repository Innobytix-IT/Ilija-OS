"""
test_scheduler.py – Tests für die Scheduler-Logik in workflow_routes.py
========================================================================
Testet: _schedule_should_fire — alle Intervalltypen, Edge Cases, Minimum-Intervall
"""
import os
import sys
import pytest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from workflow_routes import _schedule_should_fire


# ── Interval-Modus ────────────────────────────────────────────────────────────

class TestScheduleIntervalModus:

    def test_erster_lauf_ohne_last_run_feuert(self):
        """Ohne _last_run soll der Schedule sofort feuern."""
        config = {"interval_type": "interval", "minuten": 5, "sekunden": 0}
        assert _schedule_should_fire(config, datetime.now()) is True

    def test_leerer_last_run_feuert(self):
        config = {"interval_type": "interval", "minuten": 1, "_last_run": ""}
        assert _schedule_should_fire(config, datetime.now()) is True

    def test_intervall_noch_nicht_abgelaufen(self):
        last = datetime.now() - timedelta(seconds=10)
        config = {
            "interval_type": "interval",
            "minuten": 1, "sekunden": 0,
            "_last_run": last.isoformat(),
        }
        assert _schedule_should_fire(config, datetime.now()) is False

    def test_intervall_abgelaufen(self):
        last = datetime.now() - timedelta(minutes=5, seconds=1)
        config = {
            "interval_type": "interval",
            "minuten": 5, "sekunden": 0,
            "_last_run": last.isoformat(),
        }
        assert _schedule_should_fire(config, datetime.now()) is True

    def test_minimum_intervall_5_sekunden(self):
        """Intervalle unter 5 Sekunden werden auf 5s hochgesetzt."""
        last = datetime.now() - timedelta(seconds=3)
        config = {
            "interval_type": "interval",
            "minuten": 0, "sekunden": 1,  # 1s konfiguriert → wird auf 5s gesetzt
            "_last_run": last.isoformat(),
        }
        # 3 Sekunden vergangen, Minimum 5s → soll NICHT feuern
        assert _schedule_should_fire(config, datetime.now()) is False

    def test_minimum_5_sekunden_nach_ablauf(self):
        last = datetime.now() - timedelta(seconds=6)
        config = {
            "interval_type": "interval",
            "minuten": 0, "sekunden": 1,  # wird auf 5s gesetzt
            "_last_run": last.isoformat(),
        }
        # 6 Sekunden vergangen → soll feuern
        assert _schedule_should_fire(config, datetime.now()) is True

    def test_nur_sekunden_konfiguriert(self):
        last = datetime.now() - timedelta(seconds=31)
        config = {
            "interval_type": "interval",
            "minuten": 0, "sekunden": 30,
            "_last_run": last.isoformat(),
        }
        assert _schedule_should_fire(config, datetime.now()) is True

    def test_kombination_minuten_und_sekunden(self):
        last = datetime.now() - timedelta(minutes=1, seconds=31)
        config = {
            "interval_type": "interval",
            "minuten": 1, "sekunden": 30,
            "_last_run": last.isoformat(),
        }
        assert _schedule_should_fire(config, datetime.now()) is True

    def test_ungueltige_last_run_feuert(self):
        config = {
            "interval_type": "interval",
            "minuten": 5,
            "_last_run": "keine-gueltige-zeit",
        }
        assert _schedule_should_fire(config, datetime.now()) is True


# ── Täglich-Modus ─────────────────────────────────────────────────────────────

class TestScheduleTaeglich:

    def test_genau_zur_richtigen_zeit_feuert(self):
        now = datetime(2026, 4, 19, 8, 0, 0)
        config = {"interval_type": "taglich", "zeit": "08:00"}
        assert _schedule_should_fire(config, now) is True

    def test_falsche_minute_feuert_nicht(self):
        now = datetime(2026, 4, 19, 8, 1, 0)
        config = {"interval_type": "taglich", "zeit": "08:00"}
        assert _schedule_should_fire(config, now) is False

    def test_falsche_stunde_feuert_nicht(self):
        now = datetime(2026, 4, 19, 9, 0, 0)
        config = {"interval_type": "taglich", "zeit": "08:00"}
        assert _schedule_should_fire(config, now) is False

    def test_heute_bereits_gefeuert_feuert_nicht(self):
        now  = datetime(2026, 4, 19, 8, 0, 0)
        last = datetime(2026, 4, 19, 8, 0, 0)  # heute schon ausgeführt
        config = {
            "interval_type": "taglich", "zeit": "08:00",
            "_last_run": last.isoformat(),
        }
        assert _schedule_should_fire(config, now) is False

    def test_gestern_gefeuert_feuert_heute(self):
        now  = datetime(2026, 4, 19, 8, 0, 0)
        last = datetime(2026, 4, 18, 8, 0, 0)  # gestern
        config = {
            "interval_type": "taglich", "zeit": "08:00",
            "_last_run": last.isoformat(),
        }
        assert _schedule_should_fire(config, now) is True

    def test_ungueltige_zeit_feuert_nicht(self):
        now = datetime(2026, 4, 19, 8, 0, 0)
        config = {"interval_type": "taglich", "zeit": "ungueltig"}
        assert _schedule_should_fire(config, now) is False


# ── Wöchentlich-Modus ─────────────────────────────────────────────────────────

class TestScheduleWoechentlich:

    def test_richtiger_wochentag_und_uhrzeit(self):
        # Montag (weekday=0), 19. April 2026 ist ein Sonntag (weekday=6)
        # Nehmen wir einen Sonntag: datetime(2026, 4, 19) → weekday=6
        now = datetime(2026, 4, 19, 10, 0, 0)  # Sonntag
        assert now.weekday() == 6
        config = {"interval_type": "woechentlich", "wochentag": 6, "zeit": "10:00"}
        assert _schedule_should_fire(config, now) is True

    def test_falscher_wochentag_feuert_nicht(self):
        now = datetime(2026, 4, 19, 10, 0, 0)  # Sonntag = 6
        config = {"interval_type": "woechentlich", "wochentag": 0, "zeit": "10:00"}  # Montag
        assert _schedule_should_fire(config, now) is False

    def test_bereits_diese_woche_gefeuert(self):
        now  = datetime(2026, 4, 19, 10, 0, 0)  # Sonntag
        last = datetime(2026, 4, 19,  9, 0, 0)  # heute, vor 1 Stunde
        config = {
            "interval_type": "woechentlich", "wochentag": 6, "zeit": "10:00",
            "_last_run": last.isoformat(),
        }
        # Weniger als 604700s (7 Tage) vergangen → nicht feuern
        assert _schedule_should_fire(config, now) is False


# ── Unbekannter Typ ───────────────────────────────────────────────────────────

class TestScheduleUnbekannt:

    def test_unbekannter_typ_feuert_nicht(self):
        config = {"interval_type": "monatlich", "tag": 1}
        assert _schedule_should_fire(config, datetime.now()) is False

    def test_kein_typ_feuert_nicht(self):
        # Standard-Typ ist "interval" laut Code
        config = {}
        # Ohne _last_run → feuert (erster Lauf)
        assert _schedule_should_fire(config, datetime.now()) is True
