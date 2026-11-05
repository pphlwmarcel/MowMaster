# MowMaster 🌿🤖

**Der intelligente Rasenmähroboter-Slot- und Wachstums-Controller für Home Assistant.**

MowMaster macht jeden handelsüblichen Mähroboter smarter. Anstelle von starren Wochenzeitplänen ermittelt MowMaster anhand von **biologischem Rasenwachstum (GDD)** und **physikalischer Rasenfeuchte-Bilanzierung**, wann dein Rasen wirklich gemäht werden muss und wann die Bedingungen (trockener Halm, kein Hitzestress, Tierschutz) perfekt sind.

---

## 🌟 Highlights & Funktionen

- **Universell & Herstellerunabhängig:** Steuert jeden Mähroboter über die offizielle Home Assistant `lawn_mower`-Plattform (z.B. Worx Landroid, Dreame, Segway Navimow, Gardena, Husqvarna Automower, Ecovacs Goat, Roborock etc.).
- **Einsteiger & Pro direkt im Setup:**
  - **Basis-Modus:** Wähle nur deinen Mähroboter (`lawn_mower.*`), deine Wetter-Entität (`weather.*`), Rasengröße und Mähertyp.
  - **Pro-Setup direkt im ersten Schritt auswählbar:** Mit einer einfachen Checkbox kannst du sofort beim Erstellen alle Pro-Einstellungen festlegen – kein Umweg über nachträgliche Menüs nötig!
- **Natives Nässe-Konto & Feuchtemodell:**
  - Verbinde direkt deinen vorhandenen Nässe-Score (z.B. `input_number.rasen_naesse_score`), deinen Mähersensor (`binary_sensor.bobbi_regensensor`) und dein DWD-Radar.
  - Falls du noch keinen Nässe-Score hast: MowMaster simuliert die physikalische **Abtrocknungs- und Befeuchtungsrate** (mit Sonnenstrahlung, Sonnenhöhe, Wind, Taupunkt und Verdunstung) vollautomatisch intern in Python!
- **Zwei-Säulen-Berechnung:**
  1. **Wachstums-Engine (GDD & Rasenpflege):** Berechnet die *Growing Degree Days* ($T_{\text{base}} = 6^\circ\text{C}$). Berücksichtigt Düngung (mit 28-tägiger Abklingkurve) sowie Bodenfeuchte für ein dynamisches Tagesmähbudget.
  2. **Slot-Finder & Mähfreigabe:** Gibt das Mähen nur frei, wenn:
     - Der Halm oberflächlich trocken ist (Taupunktspreizung $T - T_{\text{dew}} \ge 2.5^\circ\text{C}$ & Nässe-Konto $< 3.0$ pts).
     - Kein akuter Regen fällt und kein Regenradar eine Regenfront ankündigt (Forecast-Summe $< 0.2\text{ mm}$ oder $> 60\text{ min}$ Puffer).
     - Keine Kälteschäden ($T \ge 9^\circ\text{C}$) und keine Hitzeschäden ($T \le 28^\circ\text{C}$) drohen.
     - **Herbst-Morgenfenster:** Berücksichtigt das verzögerte Aufwärmen im Herbst (Mähen erst ab Mittag bzw. wenn die Sonne hoch genug steht).
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

## 📦 Installation & Update

Kopiere den Ordner `custom_components/mowmaster` in dein Home Assistant Konfigurationsverzeichnis unter `/config/custom_components/mowmaster` und starte Home Assistant neu.

---

## ⚙️ Einrichtung (Config Flow)

1. Gehe in Home Assistant zu **Einstellungen -> Geräte & Dienste -> Integration hinzufügen**.
2. Suche nach **MowMaster**.
3. **Schritt 1 (Grundeinrichtung):**
   - Mähroboter (`lawn_mower.*`)
   - Wetterdienst (`weather.*`)
   - Rasenfläche ($m^2$)
   - Navigationstyp (*Chaos* oder *Systematisch*)
   - ☑️ **Erweiterte Pro-Einstellungen jetzt konfigurieren** (wenn angehakt, wirst du direkt durch Sensoren, Schwellenwerte und Mähzeiten geführt!).

---

## 📊 Entitäten-Übersicht

### Binäre Sensoren (`binary_sensor`)
- `binary_sensor.<name>_mowing_permitted`: **Master-Mähfreigabe**
- `binary_sensor.<name>_rain_moisture_blocked`: Nässe- & Regenblockade
- `binary_sensor.<name>_heat_blocked`: Hitzeschutz aktiv ($> 28^\circ\text{C}$)
- `binary_sensor.<name>_cold_blocked`: Kälteschutz aktiv ($< 9^\circ\text{C}$)
- `binary_sensor.<name>_wildlife_blocked`: Igelschutz aktiv (Dämmerung/Nacht)
- `binary_sensor.<name>_quiet_hours_blocked`: Ruhezeit aktiv
- `binary_sensor.<name>_seasonal_time_blocked`: Herbst-Morgenblockade

### Sensoren (`sensor`)
- `sensor.<name>_mow_urgency`: Dringlichkeit des Mähbedarfs heute (%)
- `sensor.<name>_growth_index`: Biologischer Rasenwachstumsfaktor ($x$)
- `sensor.<name>_dew_spread`: Taupunktspreizung ($T - T_{\text{dew}}$ in °C)
- `sensor.<name>_dew_point`: Berechneter oder gemessener Taupunkt (°C)
- `sensor.<name>_moisture_score`: Rasenfeuchte-Score / Nässe-Konto (pts)
- `sensor.<name>_drying_rate`: Berechnete Abtrocknungsrate (pts/h)
- `sensor.<name>_wetting_rate`: Berechnete Befeuchtungsrate (pts/h)
- `sensor.<name>_remaining_budget`: Noch benötigte Mähzeit heute (min)
- `sensor.<name>_mowed_today`: Heute bereits gemähte Zeit (min)
- `sensor.<name>_days_since_fertilized`: Tage seit der letzten Düngung (d)

### Schalter (`switch`)
- `switch.<name>_auto_mow`: **Autonome Mähsteuerung** (Start/Dockt automatisch)
- `switch.<name>_edge_cut_next`: Nächster Start mit Kantenschnitt

### Buttons (`button`)
- `button.<name>_mark_fertilized`: Rasen heute gedüngt
- `button.<name>_start_mow_now`: Mäher sofort starten
- `button.<name>_dock_mower`: Mäher zur Station senden
- `button.<name>_reset_daily_budget`: Tagesmähzeit zurücksetzen

---

## 📄 Lizenz
Veröffentlicht unter der [MIT License](LICENSE).

