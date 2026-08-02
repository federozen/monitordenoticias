import unittest
from datetime import datetime, timedelta, timezone

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
        self.assertGreaterEqual(discoveries[0]["score"], 48)
        self.assertIn(discoveries[0]["status"], {"HALLAZGO FUERTE", "HALLAZGO"})
        self.assertIn(discoveries[0]["category"], {"HISTORIA RARA", "DATO O RECORD"})
        self.assertNotIn("buena confianza", discoveries[0]["reason"].lower())
        self.assertGreaterEqual(discoveries[0]["confidence"], 50)

    def test_trusted_source_alone_does_not_create_a_finding(self):
        now = datetime.now(timezone.utc).isoformat()
        results = {
            "bbc": [{
                "titulo": "European club held a routine training session on Monday",
                "url": "https://example.com/training",
                "publisher_original": "BBC Sport",
                "fecha_publicacion": now,
            }]
        }
        discoveries = generate_discoveries(results, [], max_items=5)
        self.assertEqual(discoveries, [])

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

class V11DeskTests(unittest.TestCase):
    def test_ole_today_groups_multiple_angles(self):
        from editorial_agents.ole_today import build_ole_today
        now = datetime.now(timezone.utc).isoformat()
        items = [
            {"titulo": "River vs Central: hora, TV y formaciones", "url": "https://ole.test/river-hora", "fecha_publicacion": now, "ole_origin": "ultimas"},
            {"titulo": "River recupero a un titular para jugar con Central", "url": "https://ole.test/river-recupero", "fecha_publicacion": now, "ole_origin": "ultimas"},
        ]
        entries, groups = build_ole_today(items, [], [])
        self.assertEqual(len(entries), 2)
        self.assertTrue(groups)
        self.assertTrue(all(item.get("topic_id") for item in entries))


    def test_ole_today_handles_equal_similarity_scores(self):
        from editorial_agents.ole_today import build_ole_today
        items = [{
            "titulo": "River confirmo una baja para el partido",
            "url": "https://ole.test/river-baja",
            "fecha_publicacion": datetime.now(timezone.utc).isoformat(),
            "ole_origin": "ultimas",
        }]
        recs = [
            {
                "ole_match_title": "River confirmo una baja para el partido",
                "title": "Actualizacion externa uno",
                "action": "ACTUALIZAR",
            },
            {
                "ole_match_title": "River confirmo una baja para el partido",
                "title": "Actualizacion externa dos",
                "action": "VERIFICAR",
            },
        ]
        entries, groups = build_ole_today(items, [], recs)
        self.assertEqual(len(entries), 1)
        self.assertEqual(len(entries[0]["related_external"]), 2)
        self.assertTrue(groups)

    def test_editorial_desk_builds_free_summary_and_actions(self):
        from editorial_agents.desk import build_editorial_desk
        now = datetime.now(timezone.utc)
        themes = []
        recs = []
        for idx in range(35):
            themes.append({
                "titulo": f"Tema {idx} protagonista distinto club{idx}", "url": f"https://example.com/{idx}",
                "cant_medios": 3, "medios_originales": ["Medio A", "Medio B"],
                "tiene_ole": idx % 2 == 0, "nac": 1, "intl": 0,
                "noticias": [{"noticia": {"titulo": f"Tema {idx}", "fecha_publicacion": now.isoformat(), "url": f"https://example.com/{idx}"}, "fuente": {"nombre": "Medio A"}}],
            })
            recs.append({
                "cluster_id": f"c_{idx}", "title": f"Tema {idx} protagonista distinto club{idx}",
                "priority": 90 - idx, "action": "ACTUALIZAR" if idx < 4 else "OBSERVAR",
                "coverage_status": "CUBIERTO_CON_NOVEDAD" if idx < 4 else "CUBIERTO_IGUAL",
            })
            themes[-1]["cluster_id"] = f"c_{idx}"
        desk = build_editorial_desk(themes, [], recs, [], [], now=now, min_topics=30, max_topics=40)
        self.assertGreaterEqual(len(desk["topics"]), 30)
        self.assertLessEqual(len(desk["topics"]), 40)
        self.assertEqual(len(desk["actions"]), 4)
        self.assertTrue(desk["meta"]["cut_key"])

    def test_source_health_is_editor_friendly(self):
        from editorial_agents.source_health import build_source_editor_view
        rows = build_source_editor_view([
            {"id": "x", "nombre": "Fuente X", "estado": "error", "noticias": 0, "error": "timeout"},
            {"id": "y", "nombre": "Fuente Y", "estado": "ok", "noticias": 10, "canal": "RSS"},
        ])
        self.assertEqual(rows[0]["editorial_state"], "DEMORADA")
        self.assertEqual(rows[-1]["editorial_state"], "SALUDABLE")

class V113CutQualityTests(unittest.TestCase):
    def test_degraded_cut_preserves_previous_panorama(self):
        from editorial_agents.cut_quality import assess, merge_with_previous
        states = []
        for idx in range(73):
            states.append({
                "id": f"s{idx}",
                "estado": "ok" if idx < 22 else "error",
                "noticias": 5 if idx < 22 else 0,
                "canal": "Google News" if idx >= 25 else "RSS",
                "error": "503 Service Unavailable" if idx >= 22 else "",
            })
        quality = assess(states)
        self.assertEqual(quality["state"], "DEGRADADO")
        self.assertTrue(quality["preserve_previous"])
        current = [{"cluster_id": "c_current", "titulo": "Tema nuevo", "cant_medios": 2}]
        previous = [
            {"ClusterID": "c_current", "Titulo": "Tema nuevo", "Medios": "3"},
            {"ClusterID": "c_old", "Titulo": "Tema conservado", "Medios": "4", "TieneOle": "si", "Fuentes": []},
        ]
        merged = merge_with_previous(current, previous)
        self.assertEqual(len(merged), 2)
        carried = [row for row in merged if row.get("cluster_id") == "c_old"][0]
        self.assertTrue(carried.get("_carried_from_previous"))

    def test_complete_cut_can_replace_snapshot(self):
        from editorial_agents.cut_quality import assess
        states = [
            {"id": f"s{idx}", "estado": "ok" if idx < 60 else "error", "noticias": 5 if idx < 60 else 0, "canal": "RSS"}
            for idx in range(73)
        ]
        quality = assess(states)
        self.assertEqual(quality["state"], "COMPLETO")
        self.assertFalse(quality["preserve_previous"])


class V114StrictTimeTests(unittest.TestCase):
    def test_summary_4h_excludes_old_dated_topics(self):
        from editorial_agents.desk import build_editorial_desk
        from editorial_agents.utils import now_ar
        now = now_ar().replace(minute=30, second=0, microsecond=0)
        recent = now - timedelta(minutes=35)
        old = now - timedelta(hours=9)
        themes = [
            {
                "cluster_id": "c_recent", "titulo": "Tema reciente del corte",
                "cant_medios": 2, "noticias": [{"noticia": {"titulo": "Tema reciente", "fecha_publicacion": recent.isoformat()}, "fuente": {"nombre": "Medio"}}],
            },
            {
                "cluster_id": "c_old", "titulo": "Tema viejo que sigue en portada",
                "cant_medios": 4, "noticias": [{"noticia": {"titulo": "Tema viejo", "fecha_publicacion": old.isoformat()}, "fuente": {"nombre": "Medio"}}],
            },
        ]
        desk = build_editorial_desk(themes, [], [], [], [], now=now, min_topics=30, max_topics=40)
        titles = [item["topic"] for item in desk["topics"]]
        self.assertIn("Tema reciente del corte", titles)
        self.assertNotIn("Tema viejo que sigue en portada", titles)
        self.assertEqual(len(titles), 1)

    def test_summary_4h_excludes_explicit_old_date_in_title(self):
        from editorial_agents.desk import build_editorial_desk
        from editorial_agents.utils import TZ_AR
        now = datetime(2026, 8, 2, 18, 30, tzinfo=TZ_AR)
        themes = [{
            "cluster_id": "c_old_service",
            "titulo": "Partidos de HOY, miercoles 29 de julio: agenda y TV",
            "cant_medios": 2, "nuevo": True, "noticias": [],
        }]
        changes = [{"cluster_id": "c_old_service", "change_type": "NUEVO EN EL CORTE", "priority": 70}]
        desk = build_editorial_desk(themes, changes, [], [], [], now=now)
        self.assertEqual(desk["topics"], [])

    def test_ole_today_excludes_old_publication_and_old_explicit_title(self):
        from editorial_agents.ole_today import build_ole_today
        from editorial_agents.utils import TZ_AR
        now = datetime(2026, 8, 2, 18, 30, tzinfo=TZ_AR)
        items = [
            {"titulo": "Nota publicada hoy", "url": "https://ole.test/hoy", "fecha_publicacion": now.isoformat(), "ole_origin": "ultimas"},
            {"titulo": "Nota publicada ayer", "url": "https://ole.test/ayer", "fecha_publicacion": (now - timedelta(days=1)).isoformat(), "ole_origin": "ultimas"},
            {"titulo": "Partidos de HOY, miercoles 29 de julio", "url": "https://ole.test/29-julio", "ole_origin": "ultimas"},
        ]
        entries, _ = build_ole_today(items, [], [], now)
        self.assertEqual([item["title"] for item in entries], ["Nota publicada hoy"])

class V115OleAndSourcesTests(unittest.TestCase):
    def test_trusted_sources_use_direct_pages(self):
        from monitor_core import TODAS_FUENTES
        by_id = {item["id"]: item for item in TODAS_FUENTES}
        for source_id in ("capital", "diariouno", "uar", "cab", "aat", "actc", "conmebol", "sportspro", "frontoffice", "olympics"):
            self.assertIn(source_id, by_id)
        self.assertNotIn("news.google.com", by_id["capital"]["url"])
        self.assertNotIn("news.google.com", by_id["conmebol"]["url"])
        self.assertTrue(by_id["sportspro"].get("es_rss"))

    def test_ole_pagination_stops_at_previous_day(self):
        from unittest.mock import patch
        import monitor_core

        now = datetime.now(monitor_core._OLE_TZ)
        today = now.replace(hour=10, minute=0, second=0, microsecond=0).isoformat()
        yesterday = (now - timedelta(days=1)).replace(hour=23, minute=0, second=0, microsecond=0).isoformat()

        page1 = f'''<html><body>
        <div data-noteid="1"><a href="/futbol/nota-uno_0_a.html"><h2>Primera noticia completa publicada durante el día</h2></a><time datetime="{today}"></time></div>
        <div data-noteid="2"><a href="/futbol/nota-dos_0_b.html"><h2>Segunda noticia completa publicada durante el día</h2></a><time datetime="{today}"></time></div>
        </body></html>'''
        page2 = f'''<html><body>
        <div data-noteid="3"><a href="/futbol/nota-vieja_0_c.html"><h2>Una noticia completa perteneciente al día anterior</h2></a><time datetime="{yesterday}"></time></div>
        </body></html>'''

        class Response:
            def __init__(self, text):
                self.text = text
                self.status_code = 200
            def raise_for_status(self):
                return None

        def fake_get(url, **kwargs):
            return Response(page1 if url.endswith("/page") else page2)

        with patch.object(monitor_core.requests, "get", side_effect=fake_get):
            items = monitor_core.fetch_ultimas_ole()
        meta = monitor_core.get_ole_fetch_meta()
        self.assertEqual(len(items), 2)
        self.assertEqual(meta["status"], "estimada")
        self.assertEqual(meta["pages"], 2)
        self.assertEqual(meta["today_items"], 2)

class V115OleTodayClassificationTests(unittest.TestCase):
    def test_ole_today_includes_old_note_updated_today(self):
        from editorial_agents.ole_today import build_ole_today
        from editorial_agents.utils import TZ_AR
        now = datetime(2026, 8, 2, 18, 30, tzinfo=TZ_AR)
        items = [{
            "titulo": "Una nota anterior que recibió una actualización relevante",
            "url": "https://ole.test/actualizada",
            "fecha_publicacion": (now - timedelta(days=1)).isoformat(),
            "fecha_actualizacion": now.isoformat(),
            "ole_origin": "ultimas",
        }]
        entries, _ = build_ole_today(items, [], [], now)
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]["updated_at"])

    def test_ole_today_rejects_undated_deep_page(self):
        from editorial_agents.ole_today import build_ole_today
        from editorial_agents.utils import TZ_AR
        now = datetime(2026, 8, 2, 18, 30, tzinfo=TZ_AR)
        items = [{
            "titulo": "Una noticia sin fecha recuperada desde una página profunda",
            "url": "https://ole.test/profunda",
            "ole_origin": "ultimas",
            "ole_page": 5,
        }]
        entries, _ = build_ole_today(items, [], [], now)
        self.assertEqual(entries, [])

class V116VerifiedFreshnessTests(unittest.TestCase):
    def test_new_undated_world_cup_story_is_not_in_4h_summary(self):
        from editorial_agents.desk import build_editorial_desk
        from editorial_agents.utils import TZ_AR
        now = datetime(2026, 8, 2, 19, 20, tzinfo=TZ_AR)
        themes = [{
            "cluster_id": "c_world_final",
            "titulo": "Las claves de la final del Mundial que consagro al campeon",
            "cant_medios": 4,
            "nuevo": True,
            "noticias": [],
        }]
        changes = [{"cluster_id": "c_world_final", "change_type": "NUEVO EN EL CORTE", "priority": 90}]
        desk = build_editorial_desk(themes, changes, [], [], [], now=now)
        self.assertEqual(desk["topics"], [])

    def test_new_undated_scaloni_anniversary_is_not_in_4h_summary(self):
        from editorial_agents.desk import build_editorial_desk
        from editorial_agents.utils import TZ_AR
        now = datetime(2026, 8, 2, 19, 20, tzinfo=TZ_AR)
        themes = [{
            "cluster_id": "c_scaloni_100",
            "titulo": "Los 100 partidos de Scaloni al frente de la Seleccion Argentina",
            "cant_medios": 3,
            "nuevo": True,
            "noticias": [],
        }]
        desk = build_editorial_desk(themes, [], [], [], [], now=now)
        self.assertEqual(desk["topics"], [])

    def test_google_news_timestamp_does_not_prove_freshness(self):
        from editorial_agents.desk import build_editorial_desk
        from editorial_agents.utils import TZ_AR
        now = datetime(2026, 8, 2, 19, 20, tzinfo=TZ_AR)
        themes = [{
            "cluster_id": "c_gnews_old",
            "titulo": "Una historia antigua que Google News volvio a indexar",
            "cant_medios": 2,
            "noticias": [{
                "noticia": {
                    "titulo": "Una historia antigua que Google News volvio a indexar",
                    "fecha_publicacion": (now - timedelta(minutes=15)).isoformat(),
                    "date_trust": "discovery_timestamp",
                    "discovery_channel": "Google News",
                },
                "fuente": {"id": "gn_test", "nombre": "Google News", "url": "https://news.google.com/rss/search?q=test"},
            }],
        }]
        desk = build_editorial_desk(themes, [], [], [], [], now=now)
        self.assertEqual(desk["topics"], [])

    def test_direct_publisher_timestamp_is_accepted(self):
        from editorial_agents.desk import build_editorial_desk
        from editorial_agents.utils import TZ_AR
        now = datetime(2026, 8, 2, 19, 20, tzinfo=TZ_AR)
        themes = [{
            "cluster_id": "c_direct_recent",
            "titulo": "El club confirmo una baja para el partido de esta noche",
            "cant_medios": 2,
            "noticias": [{
                "noticia": {
                    "titulo": "El club confirmo una baja para el partido de esta noche",
                    "fecha_publicacion": (now - timedelta(minutes=15)).isoformat(),
                    "date_trust": "publisher_timestamp",
                    "discovery_channel": "RSS",
                },
                "fuente": {"id": "club", "nombre": "Club oficial", "url": "https://club.test/noticias"},
            }],
        }]
        desk = build_editorial_desk(themes, [], [], [], [], now=now)
        self.assertEqual(len(desk["topics"]), 1)

    def test_discovery_rejects_google_news_only_timestamp(self):
        from editorial_agents.discovery import generate
        now = datetime.now(timezone.utc).isoformat()
        results = {
            "gn_test": [{
                "titulo": "Historic old final story resurfaces in a search feed",
                "url": "https://news.google.com/example",
                "publisher_original": "Example",
                "fecha_publicacion": now,
                "date_trust": "discovery_timestamp",
                "discovery_channel": "Google News",
            }]
        }
        discoveries = generate(results, [], max_items=5)
        self.assertEqual(discoveries, [])

    def test_ole_today_rejects_undated_first_page_item(self):
        from editorial_agents.ole_today import build_ole_today
        from editorial_agents.utils import TZ_AR
        now = datetime(2026, 8, 2, 19, 20, tzinfo=TZ_AR)
        entries, groups = build_ole_today([{
            "titulo": "Nota sin fecha en la primera pagina",
            "url": "https://ole.test/sin-fecha",
            "ole_origin": "ultimas",
            "ole_page": 1,
        }], [], [], now)
        self.assertEqual(entries, [])
        self.assertEqual(groups, [])


class V12EditorialTrustTests(unittest.TestCase):
    def test_recent_rss_archive_story_is_rejected_without_article_metadata(self):
        from editorial_agents.desk import build_editorial_desk
        from editorial_agents.utils import TZ_AR
        now = datetime(2026, 8, 2, 19, 30, tzinfo=TZ_AR)
        themes = [{
            "cluster_id": "c_old_final",
            "titulo": "Asi fue la final del Mundial que consagro al campeon",
            "noticias": [{
                "noticia": {
                    "titulo": "Asi fue la final del Mundial que consagro al campeon",
                    "fecha_publicacion": (now - timedelta(minutes=10)).isoformat(),
                    "date_trust": "rss_publisher_timestamp",
                },
                "fuente": {"id": "medio", "nombre": "Medio"},
            }],
        }]
        desk = build_editorial_desk(themes, [], [], [], [], now=now)
        self.assertEqual(desk["topics"], [])

    def test_historical_story_needs_a_new_information_hook(self):
        from editorial_agents.desk import build_editorial_desk
        from editorial_agents.utils import TZ_AR
        now = datetime(2026, 8, 2, 19, 30, tzinfo=TZ_AR)
        base = {
            "cluster_id": "c_final_new",
            "titulo": "Video inedito: un nuevo dato de la final del Mundial",
            "noticias": [{
                "noticia": {
                    "titulo": "Video inedito: un nuevo dato de la final del Mundial",
                    "fecha_publicacion": (now - timedelta(minutes=10)).isoformat(),
                    "article_published_at": (now - timedelta(minutes=10)).isoformat(),
                    "date_trust": "article_metadata",
                },
                "fuente": {"id": "medio", "nombre": "Medio"},
            }],
        }
        desk = build_editorial_desk([base], [], [], [], [], now=now)
        self.assertEqual(len(desk["topics"]), 1)

    def test_ole_today_separates_published_and_updated(self):
        from editorial_agents.ole_today import build_ole_today
        from editorial_agents.utils import TZ_AR
        now = datetime(2026, 8, 2, 19, 30, tzinfo=TZ_AR)
        items = [
            {"titulo": "Nota nueva", "url": "https://ole.test/nueva", "fecha_publicacion": now.isoformat(), "date_trust": "article_metadata", "ole_origin": "ultimas"},
            {"titulo": "Nota vieja actualizada", "url": "https://ole.test/actualizada", "fecha_publicacion": (now - timedelta(days=1)).isoformat(), "fecha_actualizacion": now.isoformat(), "date_trust": "article_metadata", "ole_origin": "ultimas"},
        ]
        entries, groups = build_ole_today(items, [], [], now)
        self.assertEqual({row["publication_type"] for row in entries}, {"PUBLICADA_HOY", "ACTUALIZADA_HOY"})
        self.assertEqual(sum(row["piece_count"] for row in groups), 2)
