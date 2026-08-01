import unittest

from editorial_agents.curator import curate
from editorial_agents.executive import alert_message, build_report
from editorial_agents.opportunities import generate


class EditorialAgentTests(unittest.TestCase):
    def setUp(self):
        self.themes = [
            {
                "titulo": "River confirmo una baja para el partido del domingo",
                "url": "https://example.com/river",
                "cant_medios": 4,
                "medios_originales": ["Ole", "TyC Sports", "ESPN", "River Oficial"],
                "tiene_ole": False,
                "nac": 4,
                "intl": 0,
                "noticias": [
                    {
                        "noticia": {
                            "titulo": "River confirmo una baja para el domingo",
                            "url": "https://example.com/oficial",
                            "publisher_original": "River Oficial",
                            "fecha_publicacion": "2026-08-01T12:00:00-03:00",
                        },
                        "fuente": {"id": "river", "nombre": "River Oficial"},
                    },
                    {
                        "noticia": {
                            "titulo": "River tendra una baja ante su rival",
                            "url": "https://example.com/tyc",
                            "publisher_original": "TyC Sports",
                        },
                        "fuente": {"id": "tyc", "nombre": "TyC Sports"},
                    },
                ],
            }
        ]
        self.agenda = [
            {
                "accion": "SUBIR YA",
                "motivo": "4 medios lo tienen y Ole no",
                "titulo": self.themes[0]["titulo"],
                "cant_medios": 4,
                "delta": 2,
                "nuevo": True,
            }
        ]

    def test_curator_builds_explainable_recommendation(self):
        recs = curate(self.themes, self.agenda)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["action"], "PUBLICAR AHORA")
        self.assertGreaterEqual(recs[0]["confidence"], 70)
        self.assertTrue(recs[0]["notify"])
        self.assertIn("medios originales", recs[0]["reason"])

    def test_opportunities_derive_from_recommendations(self):
        recs = curate(self.themes, self.agenda)
        opps = generate(recs)
        self.assertTrue(opps)
        self.assertIn(opps[0]["format"], {"SERVICIO", "ANALISIS", "PREVIA"})

    def test_executive_report_and_alert(self):
        recs = curate(self.themes, self.agenda)
        opps = generate(recs)
        report = build_report(recs, opps, [], "HOURLY")
        self.assertIn("PRIORIDADES", report["plain_text"])
        self.assertIn("RESUMEN EDITORIAL", report["telegram_html"])
        self.assertIn("ALERTA EDITORIAL", alert_message(recs))


if __name__ == "__main__":
    unittest.main()
