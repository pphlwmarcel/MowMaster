# MowMaster 🌿🤖

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-0.2.2-blue.svg)](https://github.com/pphlwmarcel/MowMaster)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Der intelligente Rasenmähroboter-Slot- und Wachstums-Controller für Home Assistant.**

MowMaster macht jeden handelsüblichen Mähroboter smarter. Anstelle von starren Wochenzeitplänen ermittelt MowMaster anhand von **biologischem Rasenwachstum (GDD & Standort-Photoperiode)** und **physikalischer Rasenfeuchte-Bilanzierung**, *wie viel* dein Rasen heute wirklich gemäht werden muss und *wann* das perfekte Zeitfenster (trockener Halm, kein Hitzestress, kein Frost, aktiver Tierschutz) vorliegt.

---

## 🌟 Highlights & Architektur

### 1. Universell & Herstellerunabhängig
Steuert jeden Mähroboter über die offizielle Home Assistant `lawn_mower`-Plattform (z.B. Worx Landroid, Dreame, Segway Navimow, Gardena, Husqvarna Automower, Ecovacs Goat, Roborock, Bosch Indego, Mammotion Luba u.v.m.).

### 2. Einsteigerfreundlich & Pro-Konfiguration nach Maß
* **Basis-Modus:** Wähle lediglich deinen Mähroboter (`lawn_mower.*`), deine Wetter-Entität (`weather.*`), die Rasenfläche ($m^2$) und das Navigationsprinzip (*Chaos* oder *Systematisch in Bahnen*). MowMaster arbeitet sofort vollautomatisch mit physikalisch sinnvollen Standardwerten.
* **Pro-Modus (direkt beim Setup oder jederzeit über „Konfigurieren“):** Binde eigene Sensoren deiner lokalen Wetterstation, Bodenfeuchtesensoren, Sonnensensoren (Differenztemperatur / Pyranometer), Regensensoren oder DWD-Regenradar ein und passe alle Grenzwerte feingranular an.

### 3. Zwei-Säulen-Berechnung

#### 🌱 Säule 1: Biologische Wachstums-Engine & Tagesmähbudget
* **Growing Degree Days (GDD):** Berechnet die täglichen Wachstumsgradtage ($T_{\text{base}} = 6\,^\circ\text{C}$, $T_{\text{cap}} = 28\,^\circ\text{C}$) aus Wettervorhersage (`weather.get_forecasts`) und real gemessenen Tages-Min/Max-Temperaturen inklusive biologischer C3-Rasen-Optimumkurve ($16\text{–}22\,^\circ\text{C}$).
* **Weltweite astronomische Standort-Photoperiode:** Berechnet anhand des in Home Assistant hinterlegten Breitengrads (`latitude`) und des Kalendertags exakt die astronomische Tageslänge und den phänologischen Jahreszeit-Trend (funktioniert weltweit auf Nord- und Südhalbkugel). Im Spätherbst und Winter geht das Mähbudget dadurch automatisch in die Winterruhe (`0 min`).
* **Düngung & Bewässerung:** Berücksichtigt den Wachstumsschub nach einer Rasendüngung (mit 28-tägiger exponentieller Abklingkurve) sowie Bodenfeuchte bzw. regelmäßige Sommerbewässerung.

#### ☀️ Säule 2: Physikalisches Feuchtemodell & Slot-Finder
Gibt das Mähen (`binary_sensor.<name>_mowing_permitted`) nur frei, wenn alle Schutzregeln grünes Licht geben:
* **Trockener Rasenhalm:** Kombinierte Prüfung aus **Taupunktspreizung** ($T - T_{\text{dew}} \ge 2{,}5\,^\circ\text{C}$) und dem **Rasenfeuchte-Konto** (`moisture_score < 3.0 pts`).
* **Eigenes physikalisches Nässe-Konto:** Falls kein externer Nässe-Helper hinterlegt ist, bilanziert MowMaster fortlaufend die **Befeuchtungsrate** (Regen, Nebel, nächtliche Taukondensation am Halm) gegen die **Abtrocknungsrate** (Dampfdruckdefizit, Windgeschwindigkeit, Sonnenstand und Solarstrahlung).
* **Vorausschauender Regenschutz:** Sofortiger Stopp bei aktivem Regen sowie vorausschauendes Heimsenden vor eintreffenden Regenfronten über ein Regenradar (Minuten-Countdown, Niederschlagsmenge in $\text{mm}$ oder Regenwahrscheinlichkeit in $\%$).
* **Kälte- & Hitzeschutz:** Kein Mähen bei Kälte ($< 9\,^\circ\text{C}$, Schutz vor gebrochenen/gefrorenen Halmen) oder extremer Hitze ($\ge 28\,^\circ\text{C}$, Schutz vor Rasenverbrennung).
* **Jahreszeitliches Morgenfenster:** Verzögert an kurzen, kühlen Herbsttagen (`< 11,5 h` Tageslicht) den Start automatisch, bis die Sonne hoch genug steht.
* **Igelschutz & Ruhezeiten:** Kein Mähen zwischen Sonnenuntergang und Sonnenaufgang (inkl. einstellbarer Vor-/Nachlaufzeiten zum Schutz dämmerungsaktiver Kleintiere) sowie innerhalb definierter Ruhezeiten.

### 4. Intelligentes Laufzeit-, Zyklus- & Kanten-Management
* **Anti-Overmowing (Early Recall):** Holt überdimensionierte Mäher auf kleinen Flächen nach Erreichen des täglichen Mähbudgets (oder der maximalen Einzellaufzeit) vorzeitig in die Ladestation zurück.
* **Multi-Cycle:** Schickt kleinere Mäher auf großen Rasenflächen nach dem Zwischenladen automatisch erneut los, bis das Tagesbudget abgearbeitet ist.
* **Automatisches Kantenmähen:** Unterstützt ein festes Intervall (z.B. jeder 3. Start) oder das manuelle Vorwählen für die nächste Ausfahrt – inklusive Unterstützung für herstellerspezifische Dienste (wie `landroid_cloud.ots`).

---

## 📦 Installation

### Option A: Über HACS (Empfohlen)
1. Öffne **HACS** in Home Assistant.
2. Klicke oben rechts auf das Drei-Punkte-Menü $\rightarrow$ **Benutzerdefinierte Repositories**.
3. Füge die URL `https://github.com/pphlwmarcel/MowMaster` in das Feld *Repository* ein und wähle als Typ **Integration** (bzw. *Kategorie: Integration*).
4. Suche in HACS nach **MowMaster**, klicke auf **Herunterladen** und starte Home Assistant neu.

### Option B: Manuelle Installation
1. Kopiere den Ordner `custom_components/mowmaster` aus diesem Repository in dein Home Assistant Konfigurationsverzeichnis unter `/config/custom_components/mowmaster`.
2. Starte Home Assistant neu.

---

## ⚙️ Einrichtung & Konfiguration

1. Gehe in Home Assistant zu **Einstellungen $\rightarrow$ Geräte & Dienste $\rightarrow$ Integration hinzufügen**.
2. Suche nach **MowMaster**.
3. **Grundeinrichtung:**
   * **Mähroboter-Entität:** Dein `lawn_mower.*`
   * **Wetterdienst-Entität:** Dein `weather.*` (z.B. DWD, Met.no, OpenWeatherMap)
   * **Rasenfläche ($m^2$):** Netto-Rasenfläche in Quadratmetern
   * **Navigationsprinzip:** *Chaos-Prinzip / Begrenzungskabel* ($\approx 50\,\text{m}^2/\text{h}$) oder *Systematisch in Bahnen (RTK / LiDAR / Kamera)* ($\approx 120\,\text{m}^2/\text{h}$)
   * **Rasen wird im Sommer regelmäßig bewässert:** Verhindert die sommerliche Trockenheits-Drosselung des Wachstumsindex, wenn kein Bodenfeuchtesensor vorhanden ist.
   * **Erweiterte Pro-Einstellungen konfigurieren:** Wenn aktiviert, führt dich der Assistent sofort durch die 3 Experten-Schritte (Sensoren, Grenzwerte, Laufzeit/Kantenschnitt).
4. **Spätere Anpassung:** Über den Button **Konfigurieren** in der Integration können jederzeit alle **Grundeinstellungen** sowie sämtliche **Pro-Optionen** angepasst oder optionale Sensoren wieder entfernt werden.

---

## 📊 Entitäten-Übersicht (24 Entitäten)

### Binäre Sensoren (`binary_sensor`)
| Entität | Beschreibung |
| :--- | :--- |
| `binary_sensor.<name>_mowing_permitted` | **Master-Mähfreigabe** (`on` = alle Bedingungen optimal & Mähbedarf vorhanden). Enthält detaillierte Diagnose-Attribute (`blocking_reasons`, `moisture_score`, `target_daily_minutes` etc.). |
| `binary_sensor.<name>_rain_moisture_blocked` | `on`, wenn es regnet, Regen bevorsteht, der Rasen noch nass ist oder die Taupunktspreizung zu gering ist. |
| `binary_sensor.<name>_heat_blocked` | `on`, wenn die Temperatur die Hitzeschutz-Grenze (Standard $28\,^\circ\text{C}$) erreicht oder überschreitet. |
| `binary_sensor.<name>_cold_blocked` | `on`, wenn die Temperatur unter der Mindest-Mähtemperatur (Standard $9\,^\circ\text{C}$) liegt. |
| `binary_sensor.<name>_wildlife_blocked` | `on`, wenn der Igelschutz (Nacht & Dämmerungspuffer vor Sonnenuntergang / nach Sonnenaufgang) greift. |
| `binary_sensor.<name>_quiet_hours_blocked` | `on`, während die konfigurierte Ruhezeit (z.B. 20:00–08:00 Uhr) aktiv ist. |
| `binary_sensor.<name>_seasonal_time_blocked` | `on`, wenn die Sonne unter dem Horizont steht oder an kurzen, kühlen Herbsttagen der Morgen noch zu kalt ist. |
| `binary_sensor.<name>_growth_dormant_blocked` | `on`, wenn aufgrund von Kälte oder kurzen Wintertagen aktuell kein biologisches Rasenwachstum stattfindet (Winterruhe). |

### Sensoren (`sensor`)
| Entität | Einheit | Beschreibung |
| :--- | :---: | :--- |
| `sensor.<name>_mow_urgency` | `%` | Aktuelle Mähdringlichkeit heute (0–100 %). |
| `sensor.<name>_growth_index` | `x` | Biologischer Wachstumsfaktor (inkl. Attributen `growing_degree_days`, `season_factor`, `daylight_hours`, `latitude`). |
| `sensor.<name>_dew_spread` | `°C` | Aktuelle Taupunktspreizung ($T - T_{\text{dew}}$). |
| `sensor.<name>_dew_point` | `°C` | Berechneter (Magnus-Tetens) oder lokal gemessener Taupunkt. |
| `sensor.<name>_moisture_score` | `pts` | Aktuelles Rasenfeuchte-Konto (`0` = trocken, `100` = gesättigt). |
| `sensor.<name>_drying_rate` | `pts/h` | Aktuelle physikalische Abtrocknungsrate des Rasens. |
| `sensor.<name>_wetting_rate` | `pts/h` | Aktuelle physikalische Befeuchtungsrate durch Regen, Nebel oder Tau. |
| `sensor.<name>_remaining_budget` | `min` | Heute noch verbleibende Soll-Mähzeit. |
| `sensor.<name>_mowed_today` | `min` | Heute bereits absolvierte Mähzeit (übersteht auch HA-Neustarts während der Fahrt). |
| `sensor.<name>_days_since_fertilized` | `d` | Vergangene Tage seit der letzten eingetragenen Rasendüngung. |

### Schalter (`switch`)
| Entität | Beschreibung |
| :--- | :--- |
| `switch.<name>_auto_mow` | **Autonome Mähsteuerung:** Wenn aktiv, startet MowMaster den Mäher bei Freigabe automatisch und ruft ihn bei Gefahren (Regen, Hitze, Dämmerung) oder nach Erreichen des Tagesbudgets sofort in die Station zurück. |
| `switch.<name>_edge_cut_next` | Merkt für den nächsten Startbefehl einen Kantenschnitt vor (schaltet sich nach erfolgtem Start automatisch wieder zurück). |

### Tasten (`button`)
| Entität | Beschreibung |
| :--- | :--- |
| `button.<name>_mark_fertilized` | Speichert das heutige Datum als neues Düngedatum für den Wachstums-Boost. |
| `button.<name>_start_mow_now` | Startet den Mähroboter sofort (unter Berücksichtigung eines evtl. anstehenden Kantenschnitts). |
| `button.<name>_dock_mower` | Schickt den Mähroboter sofort zurück zur Ladestation. |
| `button.<name>_reset_daily_budget` | Setzt den Zähler der heute gemähten Minuten auf `0` zurück. |

---

## 🛠️ Dienste (Services)

MowMaster stellt vier Dienste bereit, die in Skripten, Automationen oder Dashboard-Karten genutzt werden können:

### 1. `mowmaster.set_fertilized`
Trägt ein Düngedatum ein (ohne Angabe von `date` wird automatisch das heutige Datum verwendet):
```yaml
action: mowmaster.set_fertilized
data:
  date: "2026-05-01"
```

### 2. `mowmaster.start_mowing`
Startet den Mähvorgang (inkl. automatischer Kantenschnitt-Logik, falls ein Intervall oder der Kantenschnitt-Schalter aktiv ist):
```yaml
action: mowmaster.start_mowing
```

### 3. `mowmaster.dock_mower`
Ruft den Mähroboter sofort zur Ladestation zurück:
```yaml
action: mowmaster.dock_mower
```

### 4. `mowmaster.reset_daily_budget`
Setzt die heute gemähte Zeit auf `0` Minuten zurück:
```yaml
action: mowmaster.reset_daily_budget
```

---

## 📄 Lizenz
Veröffentlicht unter der [MIT License](LICENSE).
