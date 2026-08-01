import unittest
import sys
import types

sys.modules.setdefault("anthropic", types.SimpleNamespace())
from datetime import datetime, timezone
from email.utils import format_datetime

import monitor_core as mc


class PublisherCountingTests(unittest.TestCase):
    def test_same_publisher_in_two_discovery_feeds_counts_once(self):
        title = "River prepara dos cambios para el próximo partido"
        resultados = {
            "gn_river": [{"titulo": title, "url": "https://a", "publisher_original": "TyC Sports"}],
            "gn_boca": [{"titulo": title, "url": "https://b", "publisher_original": "TyC Sports"}],
        }
        tendencias = mc.calcular_tendencias(resultados)
        self.assertEqual(tendencias, [])

    def test_two_original_publishers_form_a_cluster(self):
        title = "River prepara dos cambios para el próximo partido"
        resultados = {
            "gn_river": [{"titulo": title, "url": "https://a", "publisher_original": "TyC Sports"}],
            "espn": [{"titulo": title, "url": "https://b", "publisher_original": "ESPN"}],
        }
        tendencias = mc.calcular_tendencias(resultados)
        self.assertEqual(len(tendencias), 1)
        self.assertEqual(tendencias[0]["cant_medios"], 2)
        self.assertEqual(set(tendencias[0]["medios_originales"]), {"TyC Sports", "ESPN"})

    def test_rss_preserves_date_and_original_publisher(self):
        now = format_datetime(datetime.now(timezone.utc))
        xml = f"""<?xml version='1.0'?><rss><channel><item>
        <title>Una noticia deportiva suficientemente extensa - Medio Prueba</title>
        <link>https://example.com/nota</link><pubDate>{now}</pubDate>
        </item></channel></rss>"""
        items = mc.extraer_rss(xml)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["publisher_original"], "Medio Prueba")
        self.assertTrue(items[0]["fecha_publicacion"])


class VigaSnapshotTests(unittest.TestCase):
    def test_scraper_returns_source_health(self):
        import vigia
        original_sources = vigia.TODAS_FUENTES
        original_fetch = vigia.fetch_fuente
        try:
            vigia.TODAS_FUENTES = [
                {"id": "fake_ok", "nombre": "Fake OK", "url": "https://example.com"},
                {"id": "fake_bad", "nombre": "Fake Bad", "url": "https://example.com/rss", "es_rss": True},
            ]
            def fake_fetch(source):
                if source["id"] == "fake_ok":
                    return {"id": source["id"], "noticias": [{"titulo": "Noticia de prueba suficientemente extensa"}], "error": None}
                return {"id": source["id"], "noticias": [], "error": "fallo controlado"}
            vigia.fetch_fuente = fake_fetch
            resultados, estados = vigia.scrapear_todo()
            self.assertEqual(len(resultados["fake_ok"]), 1)
            self.assertEqual({e["id"]: e["estado"] for e in estados}["fake_bad"], "error")
        finally:
            vigia.TODAS_FUENTES = original_sources
            vigia.fetch_fuente = original_fetch


if __name__ == "__main__":
    unittest.main()
