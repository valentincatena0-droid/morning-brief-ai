# MORNING BRIEF AI

Un despertador de noticias automático: cada mañana investiga ~50 fuentes, verifica por corroboración, elige las 10 noticias que importan y te las entrega en una PWA instalable con notificación al teléfono. Coste: **$0**.

> Yo me despierto. El sistema ya investigó el mundo. Abro el teléfono y en pocos minutos sé qué ocurrió y por qué importa.

## Cómo funciona

```
GitHub Actions (cada 30 min) → pipeline/run.py tick
  gate horario → fetch (RSS/API) → dedupe/cluster → verificación → ranking → brief JSON
  → docs/data/*.json (historial + búsqueda) → ntfy push → GitHub Pages sirve la PWA
```

Detalles y justificación de cada decisión: [ARCHITECTURE.md](ARCHITECTURE.md).

| Módulo | Qué hace |
|---|---|
| `pipeline/fetch.py` | RSS/Atom + USGS GeoJSON en paralelo, reintentos, un feed roto no rompe nada (`health.json`) |
| `pipeline/cluster.py` | Agrupa el mismo hecho contado por distintos medios (TF‑IDF + reglas de entidades) |
| `pipeline/verify.py` | Credibilidad por fuente y corroboración: fuentes **independientes** (un wire sindicado cuenta una vez), fuente primaria, contradicciones, lenguaje atribuido → `CONFIRMED / LIKELY / DEVELOPING / UNVERIFIED` |
| `pipeline/rank.py` | Puntuación interna (impacto, escala, amplitud, confirmación, urgencia, vida cotidiana), penaliza clickbait/opinión/fluff, selección Top‑10 con diversidad *sin forzar categorías* |
| `pipeline/brief.py` | Composición extractiva: titular, resumen, por qué importa, qué sabemos / qué no, fuentes, THE BIGGEST STORY |
| `pipeline/alerts.py` | Niveles NORMAL / IMPORTANT / URGENT / BREAKING y reglas de interrupción |
| `pipeline/notify.py` | Push vía ntfy (☀️ Brief listo, 🚨 Breaking) |
| `pipeline/guards.py` | Regla financiera: cualquier acción con dinero exige confirmación explícita (nada la ejecuta) |
| `docs/` | PWA (vanilla JS, sin build): Today, History, Search, Finance, Settings, story detail + EXPLAIN |

### Sistema de credibilidad
`trust = 0.40·reputación + 0.25·historial de precisión + 0.10·transparencia de correcciones + 0.25·fuente primaria` (valores editables en `config/sources.yaml`; son *priors* de criterio editorial, no mediciones). La confianza de una noticia = noisy‑OR sobre propietarios independientes + bonus por fuente primaria − penalización por disputa o por depender solo de afirmaciones atribuidas.

### Niveles de prioridad
| Nivel | Criterio | Push |
|---|---|---|
| NORMAL | score < 48 | no |
| IMPORTANT | ≥ 48 | no (entra al brief) |
| URGENT | ≥ 66, confirmada/probable, ≤ 12 h | solo si lo activas |
| BREAKING | ≥ 80, confirmada/probable, ≤ 3 h, ≥ 3 propietarios independientes (o primaria + 2), impacto alto | **sí** (máx. 3/día, respeta horas de silencio) |

Umbrales en `pipeline/rank.py → THRESHOLDS`.

### Honestidad de contenido
El modo por defecto es **extractivo**: cada frase sale de un feed real y se atribuye al medio. No se inventan noticias, fuentes, citas ni datos (hay un test que lo comprueba). Lo político se presenta como declaración (“X said”), no como hecho. `EXPLAIN` separa FACTS / POSSIBLE CONSEQUENCES / ANALYSIS; el análisis solo existe si activas el LLM opcional (o copias el prompt anclado a un asistente).
Los textos vienen en el idioma de la fuente (inglés). La traducción al español es una mejora opcional vía LLM (`llm.language: es`).

## Instalación (≈10 min, sin coste)

1. **Crea un repositorio en GitHub** (público recomendado: Actions y Pages ilimitados) y sube este proyecto.
2. **Genera tu topic privado**: `python scripts/init_secrets.py` → copia el valor.
3. **Secrets/variables** (Settings → Secrets and variables → Actions):
   - Secret `NTFY_TOPIC` = el topic generado.
   - Variable `APP_URL` = `https://TU-USUARIO.github.io/TU-REPO/`
   - (Opcional) Secret `GEMINI_API_KEY` y `llm.enabled: true` para EXPLAIN con IA.
4. **Pages**: Settings → Pages → Deploy from branch → `main` / carpeta `/docs`.
5. **Zona horaria/hora**: edita `config/settings.yaml` (`brief.time`, `brief.timezone`, `brief.frequency`).
6. **Móvil**: instala la app **ntfy** (iOS/Android), suscríbete al topic. Abre la URL de Pages en el teléfono → *Añadir a pantalla de inicio* (iPhone: Safari → Compartir; Android: Chrome → Instalar).
7. **Prueba**: Actions → *morning-brief* → Run workflow → `force: true`. Debe llegarte ☀️ MORNING BRIEF READY.

Después es autónomo: cada tick de 30 min decide si toca brief (hora local ≥ tu hora, día permitido, aún no hay brief de hoy; tolera retrasos de GitHub hasta 6 h y el cambio horario).

## Ejecutar en local
```bash
pip install -r requirements.txt
cp .env.example .env            # solo local; nunca se commitea
python -m unittest discover -s tests            # 44 pruebas offline
python -m pipeline.run tick --force --dry-run   # brief real, sin enviar push
python -m pipeline.run tick --now 2026-09-20T11:00:00Z --fixtures tests/fixtures --out /tmp/demo --dry-run  # simula las 7:00 AM con datos de prueba
python -m pipeline.run text                     # imprime el último brief en texto
cd docs && python -m http.server 8000           # PWA en http://localhost:8000
```

## Configuración
| Qué | Dónde |
|---|---|
| Hora, zona, frecuencia (Every day / Weekdays / Custom) | `config/settings.yaml → brief` (la pantalla Settings de la app genera el texto exacto a pegar) |
| Alertas (niveles, máx/día, horas de silencio) | `alerts` |
| Fuentes y su credibilidad | `config/sources.yaml` |
| Intereses, watchlist financiera, tema, memoria de lectura | **en tu dispositivo** (Settings/Finance) |
| Umbrales de ranking/prioridad | `pipeline/rank.py → THRESHOLDS` |

**Cambiar la hora**: la app no puede escribir en tu repo (a propósito: no guarda credenciales). Settings genera el fragmento YAML y abre `settings.yaml` en GitHub; commit → el siguiente tick lo aplica.

**Añadir una fuente**: agrega un bloque en `sources.yaml` con `name, owner, reputation, accuracy, corrections, primary, feeds[{url, category}]`. Sin código. Si no tiene RSS, usa un feed de Google News con `site:dominio` y `headline_only: true`. Un formato nuevo no‑RSS requiere un parser en `fetch.py` (ver `usgs_geojson`).

### Variables de entorno (`.env.example`)
`NTFY_TOPIC` (secreto), `NTFY_TOKEN` (opcional), `APP_URL`, `GEMINI_API_KEY` (opcional). Nada de esto llega al frontend (hay tests que lo verifican).

## Seguridad
Sin contraseñas ni claves en el repo; secretos solo en GitHub Secrets. La PWA es estática, con CSP estricta (`script-src 'self'`), texto siempre vía `textContent`, enlaces validados a `http(s)`, `rel=noopener`. Separación frontend/backend total: el backend es un job que solo escribe `docs/data/`. Permisos mínimos del workflow: `contents: write`. HTTPS por defecto (Pages, ntfy).
**Dinero**: no existe integración con brokers, bancos ni pagos. `finance.trading_enabled: true` hace que el pipeline se niegue a arrancar. La pestaña Finance es solo lectura.

## Solución de problemas
| Síntoma | Causa / arreglo |
|---|---|
| No llega el brief | Actions → ver el run; el log muestra `schedule: …` con el motivo. Revisa `NTFY_TOPIC` |
| Llega a otra hora | `brief.timezone` no es la de tu zona; GitHub puede retrasar cron 5–30 min |
| “Low source availability” | Feeds caídos/bloqueados: mira `docs/data/health.json` → `failed`; corrige o quita la URL en `sources.yaml` |
| Un feed devuelve 403 | Algunos medios bloquean bots; no se evade: usa otra fuente/alternativa legítima |
| Poco contenido | Es intencional: solo entra lo que supera el umbral de calidad; lo no verificado sale etiquetado |
| Push en iPhone | Usa la app ntfy (APNs). Web Push directo requiere un servidor de suscripciones (ver Roadmap) |
| La app muestra datos viejos | Cierra y reabre (el service worker actualiza en segundo plano) |

## Roadmap
Web Push propio (VAPID + Cloudflare Worker free tier), traducción/EXPLAIN con IA por defecto, más parsers de fuentes oficiales, ajuste de umbrales con tu feedback.
