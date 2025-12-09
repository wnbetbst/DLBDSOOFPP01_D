# Studienverlaufs-Dashboard (Python)

Ein textbasiertes Dashboard zur Abbildung des Studienverlaufs im Studiengang **B.Sc. Cyber Security**.  
Das System visualisiert ECTS-Fortschritt, Notenentwicklung, Modulstatus und individuelle Studienziele und basiert auf einer klar strukturierten, objektorientierten Python-Architektur.

Dieses Projekt wurde im Rahmen des Moduls *„Projekt: Objektorientierte und funktionale Programmierung mit Python“* entwickelt und dient als prototypische Umsetzung eines modellgetriebenen Softwareentwurfs.

---

## Features

- Darstellung des gesamten Studienprogramms (Semester, Module, Prüfungsleistungen)
- Verwaltung der Modulzustände:  
  *geplant*, *belegt*, *abgeschlossen*, *anerkannt*
- Automatische Berechnung:
  - ECTS-Fortschritt
  - aktueller Notenschnitt (GPA)
  - belegte und abgeschlossene Module
- Benutzerdefinierte Studienziele
- JSON-basierte Persistenz (automatische Speicherung)
- Klar strukturierte OOP-Architektur (Domain, ViewModel, Persistence, CLI)
- Einfache Erweiterbarkeit für GUI-, Web- oder API-Umgebungen

---


---

## Installation

### **1. Voraussetzungen**
- Python **3.10+**
- Terminal / Kommandozeile  
  (Windows: PowerShell, macOS/Linux: Terminal)

Empfohlen:
- Virtuelle Umgebung (`venv`)
- Editor wie VS Code

---

### **2. Projekt herunterladen**

Projektdateien in einen Ordner speichern, z. B.: /Dashboard/


---

### **3. Python installieren**

**Windows**  
https://www.python.org/downloads → *Add Python to PATH* aktivieren.

**macOS**
```bash
brew install python
```

**Linux (Debian/Ubuntu)**
```bash
sudo apt update
sudo apt install python3 python3-pip
```

## 4. Virtuelle Umgebung anlegen (optional)

```bash
python -m venv venv
```
Aktivieren:

**Windows**
```bash
venv\Scripts\activate
```
**macOS/Linux**
```bash
source venv/bin/activate
```

## 5. Anwendung starten

```bash
python dashboard.py



