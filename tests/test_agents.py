import unittest
from datetime import datetime, timezone

from editorial_agents.coverage import enrich_themes
from editorial_agents.curator import curate
from editorial_agents.discovery import generate as generate_discoveries
from editorial_agents.executive import alert_message, build_report
from editorial_agents.briefing import build as build_briefing
from editorial_agents.opportunities import generate as generate_opportunities


class EditorialAgentTests(unittest.TestCase):
    def setUp(self):
        now = datetime.now(timezone.utc).isoformat()
        self.themes = [
            {
                "titulo": "River confirmo una baja para el partido del domingo",
                "url": "https://example.com/river",
                "cant_medios": 3,
                "medios_originales": ["TyC Sports", "ESPN", "River Oficial"],
                "tiene_ole": False,
                "noticias": [
                    {
                        "noticia": {
                            "titulo": "River confirmo una baja para el domingo",
                            "url": "https://example.com/oficial",
                            "publisher_original": "River Oficial",
                            "fecha_publicacion": now,
                        },
                        "fuente": {"id": "river", "nombre": "River Oficial"},
                    },
                    {
                        "noticia": {
                            "titulo": "River tendra una baja ante su rival",
                            "url": "https://example.com/tyc",
                            "publisher_original": "TyC Sports",
                            "fecha_publicacion": now,
                        },
                        "fuente": {"id": "tyc", "nombre": "TyC Sports"},
                    },
                ],
            }
        ]
        self.agenda = [{
            "accion": "SUBIR YA", "motivo": "tres medios lo tienen",
            "titulo": self.themes[0]["titulo"], "cant_medios": 3,
            "delta": 2, "nuevo": True,
        }]

    def test_covered_equal_is_not_recommended_as_new(self):
        enriched = enrich_themes(self.themes, [{
            "titulo": "River confirmo una baja para el partido del domingo",
            "url": "https://ole.example/river",
        }])
        rec = curate(enriched, self.agenda)[0]
        self.assertEqual(rec["coverage_status"], "CUBIERTO_IGUAL")
        self.assertEqual(rec["action"], "OBSERVAR")
        self.assertLess(rec["priority"], 60)

    def test_uncovered_recent_theme_is_actionable(self):
        enriched = enrich_themes(self.themes, [])
        rec = curate(enriched, self.agenda)[0]
        self.assertEqual(rec["coverage_status"], "NO_CUBIERTO")
        self.assertEqual(rec["action"], "PUBLICAR AHORA")
        self.assertTrue(rec["notify"])

    def test_discovery_prioritizes_rare_international_story(self):
        now = datetime.now(timezone.utc).isoformat()
        results = {
            "bbc": [{
                "titulo": "Goalkeeper scores historic 98th-minute goal and sends tiny club up",
                "url": "https://example.com/keeper",
                "publisher_original": "BBC Sport",
                "fecha_publicacion": now,
            }],
            "guardian": [{
                "titulo": "Goalkeeper scores historic goal in 98th minute to win promotion",
                "url": "https://example.com/keeper2",
                "publisher_original": "The Guardian",
                "fecha_publicacion": now,
            }],
        }
        discoveries = generate_discoveries(results, [], max_items=5)
        self.assertTrue(discoveries)
        self.assertGreaterEqual(discoveries[0]["score"], 58)
        self.assertIn(discoveries[0]["category"], {"HISTORIA RARA", "DATO O RECORD"})

    def test_discovery_returns_best_candidates_even_below_strong_threshold(self):
        now = datetime.now(timezone.utc).isoformat()
        results = {
            "bbc": [{
                "titulo": "European club changes its stadium access system for supporters",
                "url": "https://example.com/stadium",
                "publisher_original": "BBC Sport",
                "fecha_publicacion": now,
            }]
        }
        discoveries = generate_discoveries(results, [], max_items=5)
        self.assertEqual(len(discoveries), 1)
        self.assertIn(discoveries[0]["status"], {"HALLAZGO FUERTE", "CANDIDATO", "EXPLORAR"})

    def test_briefing_reports_only_real_delta(self):
        previous = [{
            "ClusterID": "c_test", "Titulo": "Tema de prueba", "Medios": "2",
            "TieneOle": "no", "Accion": "OBSERVAR", "Fuentes": [],
        }]
        current = [{
            "cluster_id": "c_test", "titulo": "Tema de prueba", "cant_medios": 4,
            "tiene_ole": False, "accion": "ACTUALIZAR", "fuentes": [],
        }]
        recs = [{
            "cluster_id": "c_test", "action": "ACTUALIZAR", "coverage_status": "CUBIERTO_CON_NOVEDAD",
            "reason": "aparecio un dato nuevo",
        }]
        changes, summary = build_briefing(current, previous, recs, [], [])
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["change_type"], "ACTUALIZAR NOTA")
        self.assertIn("paso de 2 a 4", changes[0]["what_changed"])
        self.assertIn("QUE CAMBIO PARA AGREGAR", summary["plain_text"])

    def test_report_separates_operations_and_findings(self):
        recs = curate(enrich_themes(self.themes, []), self.agenda)
        discoveries = [{
            "discovery_id": "d_1", "category": "HISTORIA RARA", "title": "Historia inesperada",
            "score": 80, "value_argentina": 70, "reason": "rareza", "notify": True,
        }]
        opps = generate_opportunities(recs, discoveries)
        report = build_report(recs, discoveries, opps, [], "HOURLY")
        self.assertIn("NOVEDADES SIN CUBRIR", report["plain_text"])
        self.assertIn("HALLAZGOS DEL EXTERIOR", report["plain_text"])
        self.assertIn("ALERTA EDITORIAL", alert_message(recs, discoveries))


if __name__ == "__main__":
    unittest.main()
