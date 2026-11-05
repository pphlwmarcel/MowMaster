# MowMaster 🌿🤖

**Der intelligente Rasenmähroboter-Slot- und Wachstums-Controller für Home Assistant.**

MowMaster macht jeden handelsüblichen Mähroboter smarter. Anstelle von starren Wochenzeitplänen ermittelt MowMaster anhand von **biologischem Rasenwachstum (GDD)** und **meteorologischer Taupunktanalyse**, wann dein Rasen wirklich gemäht werden muss und wann die Bedingungen (trockener Halm, kein Hitzestress, Tierschutz) perfekt sind.

---

## 🌟 Highlights & Funktionen

- **Universell & Herstellerunabhängig:** Steuert jeden Mähroboter über die offizielle Home Assistant `lawn_mower`-Plattform (z.B. Worx Landroid, Dreame, Segway Navimow, Gardena, Husqvarna Automower, Ecovacs Goat, Roborock etc.).
- **Minimaler Setup-Aufwand (Einsteiger-Modus):**
  - Benötigt lediglich deine `lawn_mower`-Entität und deine bestehende `weather`-Entität.
  - Ermittelt Taupunkt und Oberflächentrocknung vollautomatisch über die meteorologische Magnus-Tetens-Formel.
- **Pro-Optionen für Wetterstationen & Feuchtesensoren:**
  - Beliebige Sensoren für Außentemperatur, Luftfeuchte, Regenmesser, Live-Regenradar (z.B. DWD Radar), Sonneneinstrahlung ($W/m^2$ oder Lux), Wind und Bodenfeuchte können als Präzisionsquelle eingebunden werden.
- **Zwei-Säulen-Berechnung:**
  1. **Wachstums-Engine (GDD & Rasenpflege):** Berechnet die *Growing Degree Days* ($T_{\text{base}} = 6^\circ\text{C}$). Berücksichtigt Düngung (mit 28-tägiger Abklingkurve) sowie Bodenfeuchte für ein dynamisches Tagesmähbudget.
  2. **Slot-Finder & Mähfreigabe:** Gibt das Mähen nur frei, wenn:
     - Der Halm oberflächlich trocken ist (Taupunktspreizung $T - T_{\text{dew}} \ge 2.5^\circ\text{C}$).
     - Kein akuter Regen fällt und kein Regenradar eine Regenfront ankündigt.
     - Keine Rasenverbrennung durch Hitze droht ($< 28^\circ\text{C}$).
     - **Igelschutz aktiv:** Kein Mähen zwischen Sonnenuntergang und Sonnenaufgang (plus konfigurierbare Pufferzeiten).
     - Keine Ruhezeiten verletzt werden.
- **Flächen- & Laufzeit-Management:**
  - Unterstützt sowohl **Chaos-/Kabelmäher** als auch **systematische Bahnmäher (RTK / LiDAR / Kamera)**.
  - **Anti-Overmowing / Early Recall:** Holt große Mäher auf kleinen Rasenflächen vorzeitig zurück, um Spurbildung und Halmschäden zu verhindern.
  - **Multi-Cycle:** Schickt kleine Mäher bei großen Wiesen nach dem Wiederaufladen automatisch erneut los, falls das Tagesbudget noch nicht erreicht ist.
- **Automatisches Kantenmähen:**
  - Eigener Schalter ("Nächster Start: Kantenschnitt") und konfigurierbares Intervall (z.B. jeden 3. Start).
  - Unterstützt herstellerspezifische Dienste (z.B. `landroid_cloud.ots`).

---

## 📦 Installation

### Methode 1: Über HACS (Empfohlen)
1. Öffne **HACS** in Home Assistant.
2. Klicke oben rechts auf das Dreipunkt-Menü und wähle **Benutzerdefinierte Repositories**.
3. Füge die URL dieses Repositories ein und wähle als Kategorie **Integration**.
4. Suche nach **MowMaster**, klicke auf **Herunterladen** und starte Home Assistant neu.

### Methode 2: Manuelle Installation
1. Kopiere den Ordner `custom_components/mowmaster` in dein Home Assistant Konfigurationsverzeichnis unter `/config/custom_components/mowmaster`.
2. Starte Home Assistant neu.

---

## ⚙️ Einrichtung (Config Flow)

1. Gehe in Home Assistant zu **Einstellungen -> Geräte & Dienste -> Integration hinzufügen**.
2. Suche nach **MowMaster**.
3. **Schritt 1 (Basis-Setup):**
   - Wähle deinen **Mähroboter** (`lawn_mower.*`).
   - Wähle deine **Wetter-Entität** (`weather.*`).
   - Gib deine **Rasenfläche** in $m^2$ ein.
   - Wähle den **Navigationstyp** (*Chaos-Prinzip* oder *Systematisch RTK/LiDAR*).
4. Fertig! MowMaster erstellt sofort das passende Gerät mit allen Sensoren, Schaltern und Buttons.

### Pro-Einstellungen anpassen
Klicke jederzeit auf **Konfigurieren** auf der MowMaster-Integrationskarte:
- **Lokale Wetter- & Bodensensoren:** Überschreibe Temperatur, Feuchte, Regenmesser, DWD-Regenradar, Helligkeit oder Bodenfeuchte mit deinen lokalen Sensoren.
- **Grenzwerte & Schutzregeln:** Justiere Taupunktspreizung, Maximaltemperatur, Igelschutz-Pufferzeiten und Ruhezeiten.
- **Mähzeiten, Akku & Kantenmähen:** Passe $m^2/h$-Leistung, Mindestakkustand, maximale Einzellaufzeit und Kantenmäh-Dienste an.

---

## 📊 Entitäten-Übersicht

### Binäre Sensoren (`binary_sensor`)
| Entität | Beschreibung |
|---|---|
| `binary_sensor.<name>_mowing_permitted` | **Master-Mähfreigabe:** Grünes Licht, wenn alle Bedingungen optimal sind. |
| `binary_sensor.<name>_rain_moisture_blocked` | Aktiv bei akutem Regen, Regenfront oder zu nassem Tau. |
| `binary_sensor.<name>_heat_blocked` | Aktiv bei Temperaturen über der Hitzegrenze ($> 28^\circ\text{C}$). |
| `binary_sensor.<name>_wildlife_blocked` | Aktiv bei Dämmerung & Nacht zum Schutz von Igeln und Wildtieren. |
| `binary_sensor.<name>_quiet_hours_blocked` | Aktiv während definierter Ruhezeiten (z.B. 20:00 - 08:00 Uhr). |

### Sensoren (`sensor`)
| Entität | Einheit | Beschreibung |
|---|---|---|
| `sensor.<name>_mow_urgency` | `%` | Dringlichkeit des Mähbedarfs heute. |
| `sensor.<name>_growth_index` | `x` | Aktueller Wachstumsfaktor (1.0 = normal, 2.0 = Wachstumsschub). |
| `sensor.<name>_dew_spread` | `°C` | Aktuelle Taupunktspreizung ($T - T_{\text{dew}}$). |
| `sensor.<name>_moisture_score` | `%` | Geschätzte Rasennässe (0 = trocken, 100 = durchnässt). |
| `sensor.<name>_remaining_budget` | `min` | Noch benötigte Mähzeit für den heutigen Tag. |
| `sensor.<name>_mowed_today` | `min` | Heute bereits gemähte Gesamtlaufzeit. |
| `sensor.<name>_days_since_fertilized` | `d` | Vergangene Tage seit der letzten Düngung. |

### Schalter (`switch`)
| Entität | Beschreibung |
|---|---|
| `switch.<name>_auto_mow` | **Autonome Mähsteuerung:** Wenn eingeschaltet, startet und stoppt MowMaster den Mäher vollautomatisch bei idealen Zeitfenstern. |
| `switch.<name>_edge_cut_next` | Schaltet für den nächsten Start gezielt den Kantenschnitt ein. |

### Buttons (`button`)
| Entität | Beschreibung |
|---|---|
| `button.<name>_mark_fertilized` | Markiert den heutigen Tag als Düngedatum (aktiviert den Wachstumsschub). |
| `button.<name>_start_mow_now` | Startet den Mäher manuell sofort. |
| `button.<name>_dock_mower` | Sendet den Mäher sofort zur Ladestation zurück. |
| `button.<name>_reset_daily_budget` | Setzt das gemähte Tagesbudget auf 0 zurück. |

---

## 🛠️ Dienste (Services)

- `mowmaster.set_fertilized`: Trägt ein Düngedatum ein (`date: "YYYY-MM-DD"` oder heute).
- `mowmaster.start_mowing`: Startet den Mähroboter.
- `mowmaster.dock_mower`: Ruft den Mähroboter zurück.
- `mowmaster.reset_daily_budget`: Setzt die Mähminuten für heute zurück.

---

## 🧮 Wissenschaftlicher Hintergrund

### 1. Taupunkt & Abtrocknung (Magnus-Tetens)
$$T_{\text{dew}} = \frac{237.7 \cdot \alpha}{17.27 - \alpha} \quad \text{mit} \quad \alpha = \frac{17.27 \cdot T}{237.7 + T} + \ln\left(\frac{RH}{100}\right)$$
Trockener Halm wird erreicht, sobald die Spreizung $T - T_{\text{dew}} \ge 2.5^\circ\text{C}$ beträgt. Liegt die Spreizung darunter, verklebt geschnittenes Gras am Mähwerk und Klumpenbildung schädigt die Grasnarbe.

### 2. Biologisches Rasenwachstum (GDD)
$$GDD = \max\left(0, \frac{\min(T_{\max}, 28) + \max(T_{\min}, 6)}{2} - 6\right)$$
Rasen wächst ab ca. $6^\circ\text{C}$ Basistemperatur. Bei Sommerhitze ($> 28^\circ\text{C}$) schaltet der Stoffwechsel in einen Hitzeschutzmodus. Düngung führt zu einem exponentiell abklingenden Wachstumsschub über 28 Tage:
$$\text{Faktor}_{\text{Düngung}} = 1.0 + 0.7 \cdot e^{-0.075 \cdot \text{Tage}}$$

---

## 📄 Lizenz
Veröffentlicht unter der [MIT License](LICENSE).

