---
name: weather
description: Get current weather and forecasts (no API key required).
homepage: https://wttr.in/:help
metadata: { "openclaw": { "emoji": "🌤️", "requires": { "bins": ["curl"] } } }
---

# Weather

Only output a short summary (no steps, no code blocks).

## City selection (important)

Rules:
- If the user explicitly names a city, use that city.
- If the user does not name a city, infer it from IP location.

IP location (no key, JSON):

```bash
curl -s "https://ipinfo.io/json"
```

Use the `city` field as the default city.

## Output format (important)

只输出以下 4 行（不需要解释、步骤或命令）：
- 天气：<条件>
- 温度：<温度>
- 湿度：<湿度>
- 风力：<风向风速>

## wttr.in (primary)

Quick one-liner (for reference):

```bash
curl -s "wttr.in/{CITY}?format=3"
# Output: {CITY}: ⛅️ +8°C
```

Compact format (for reference):

```bash
curl -s "wttr.in/{CITY}?format=%l:+%c+%t+%h+%w"
# Output: {CITY}: ⛅️ +8°C 71% ↙5km/h
```

Full forecast (for reference):

```bash
curl -s "wttr.in/{CITY}?T"
```

Format codes: `%c` condition · `%t` temp · `%h` humidity · `%w` wind · `%l` location · `%m` moon

Tips:

- URL-encode spaces: `wttr.in/New+York`
- Airport codes: `wttr.in/JFK`
- Units: `?m` (metric) `?u` (USCS)
- Today only: `?1` · Current only: `?0`
- PNG: `curl -s "wttr.in/Berlin.png" -o /tmp/weather.png`

## Open-Meteo (fallback, JSON)

Free, no key, good for programmatic use:

```bash
curl -s "https://api.open-meteo.com/v1/forecast?latitude=51.5&longitude=-0.12&current_weather=true"
```

Find coordinates for a city, then query. Returns JSON with temp, windspeed, weathercode.

Docs: https://open-meteo.com/en/docs
