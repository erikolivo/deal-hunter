# Deal Hunter (Amazon)

Sistema automatizado de detección de descuentos reales (60-90%) en deals de Amazon,
vía la API "Real-Time Amazon Data" en RapidAPI. Alerta por Telegram.

Corre en GitHub Actions sin servidor propio, persistiendo estado por commits a git.

## Por qué existe

El % de descuento que reporta cualquier fuente depende de un `list_price` que no controlamos.
Se confirmó con datos reales de esta misma API que el campo `savings_percentage` y el
`deal_badge` **pueden no coincidir** para el mismo producto. Por eso este sistema:

1. **Ignora ambos campos** de la API y recalcula el % de descuento a partir de
   `list_price` y `deal_price`.
2. Construye su propio **histórico de precios por ASIN**, y valida cada descuento
   contra lo que él mismo ha observado — no contra lo que la API afirma.

## Arquitectura

```
src/hunter/
├── config.py               # Umbrales ajustables (dataclass frozen)
├── models.py               # Product recalcula % de descuento, ignora deal_badge
├── amazon_deals_client.py   # Cliente del endpoint deals-v2, paginado, con retry
├── state_store.py           # Histórico de precios por ASIN + cooldown de alertas
├── discount_engine.py       # Decide STRONG_BUY / WATCH / SUSPICIOUS_ANCHOR / OUT_OF_RANGE
├── telegram_notifier.py     # Incluye tiempo restante del deal
└── main.py                  # Orquesta el pipeline

.github/workflows/hunt.yml   # Corre cada 2h, persiste estado vía git commit
```

### Veredictos

| Veredicto | Significado |
|---|---|
| 🟢 `STRONG_BUY` | Descuento en rango, `list_price` validado contra ≥3 observaciones propias |
| 🟡 `WATCH` | Descuento en rango pero aún sin suficiente historial para confiar en el ancla |
| 🚫 `SUSPICIOUS_ANCHOR` | El `list_price` actual se disparó respecto al histórico propio |
| ⚪ `OUT_OF_RANGE` | Fuera de 60-90%, o fuera del rango de precio configurado |

## Setup

### 1. Credenciales (GRATIS)

- **RapidAPI key**: regístrate en rapidapi.com → busca "Real-Time Amazon Data" → suscríbete al plan gratuito.
- **Bot de Telegram**: [@BotFather](https://t.me/BotFather) para el token.
- **Chat ID**: envía un mensaje a tu bot, luego visita `https://api.telegram.org/bot<TOKEN>/getUpdates` para obtener tu `chat_id`.

### 2. Local

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt

export RAPIDAPI_KEY="tu_key"
export TELEGRAM_BOT_TOKEN="tu_token"
export TELEGRAM_CHAT_ID="tu_chat_id"
export DRY_RUN=true

PYTHONPATH=src python -m hunter.main
```

Corre con `DRY_RUN=true` unos días para calibrar antes de activar alertas reales.

### 3. GitHub Actions

1. Push a GitHub.
2. **Settings → Secrets and variables → Actions → New repository secret**:
   - `RAPIDAPI_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. **Settings → Actions → General → Workflow permissions → Read and write permissions**
4. Revisa el límite de tu plan gratuito en RapidAPI. El workflow corre cada 2h (~720 runs/mes).

### 4. Tests

```bash
pip install -r requirements-dev.txt
PYTHONPATH=src pytest tests/ -v
```

## Notas sobre la API

- El parámetro `discount_range` es un bucket amplio, no un filtro preciso. Por eso `main.py` pide amplio y filtra con `discount_engine`.
- La API puede repetir `deal_id` para variantes (color, tamaño); `amazon_deals_client.py` deduplica por `product_asin`.
- Respuesta anidada en `data.deals`, no en la raíz.

## Antes de arriesgar dinero real

1. `DRY_RUN=true` mínimo una semana.
2. Revisa cuántos `STRONG_BUY` vs. `SUSPICIOUS_ANCHOR` — si todo es sospechoso, ajusta `anchor_inflation_ratio` en `config.py`.
3. Valida el precio en Keepa o CamelCamelCamel como segunda opinión.
4. Este sistema detecta — no compra ni gestiona logística.
