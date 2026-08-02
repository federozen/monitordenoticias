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
